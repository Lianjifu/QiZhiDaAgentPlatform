"""Roundtrip integration tests: register an OpenAPI/MCP tool and exercise
its invocation through the real runtime adapters + router.

These tests don't use the in-memory FakeOpenAPIRuntime / FakeMCPRuntime
fakes; instead they wire the real `OpenAPIRuntimeAdapter` and
`MCPRuntimeAdapter` against an httpx client whose transport is mocked.
That way we exercise the full path: spec extraction → adapter.invoke →
envelope construction → response parsing → ToolCall persistence.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

import httpx
from _tool_integration_in_memory import (
    CollectingEventPublisher,
    FakeCustomInvoker,
    InMemoryToolCallRepository,
    InMemoryToolRepository,
)
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from qzdap.modules.tool.adapter.adapters.mcp_runtime import MCPRuntimeAdapter
from qzdap.modules.tool.adapter.adapters.openapi_runtime import (
    OpenAPIRuntimeAdapter,
)
from qzdap.modules.tool.adapter.http.router import build_router, tool_dependency
from qzdap.modules.tool.application.services import ToolService

TENANT = UUID("00000000-0000-0000-0000-000000000001")
WORKSPACE = UUID("00000000-0000-0000-0000-000000000002")


def _client_with_handler(handler) -> httpx.AsyncClient:
    """httpx AsyncClient that routes every request through `handler`."""
    transport = httpx.MockTransport(handler)
    return httpx.AsyncClient(transport=transport, base_url="http://upstream.test")


def _build_app(openapi_client: httpx.AsyncClient, mcp_client: httpx.AsyncClient):
    tools = InMemoryToolRepository()
    calls = InMemoryToolCallRepository()
    custom = FakeCustomInvoker()
    openapi_rt = OpenAPIRuntimeAdapter(http=openapi_client)
    mcp_rt = MCPRuntimeAdapter(http=mcp_client)
    events = CollectingEventPublisher()
    svc = ToolService(
        tools=tools,
        calls=calls,
        custom=custom,
        openapi=openapi_rt,
        mcp=mcp_rt,
        events=events,
    )
    app = FastAPI(title="tool-roundtrip-test")
    from qzdap_http.error_envelope import error_envelope_middleware
    from starlette.middleware.base import BaseHTTPMiddleware

    app.add_middleware(BaseHTTPMiddleware, dispatch=error_envelope_middleware)  # type: ignore[arg-type]
    app.include_router(build_router())

    async def _provide() -> AsyncIterator[ToolService]:
        yield svc

    app.dependency_overrides[tool_dependency] = _provide
    return app, ctx_fixture(tools, calls, openapi_client, mcp_client)


def ctx_fixture(tools, calls, openapi_client, mcp_client):
    return {
        "tools": tools,
        "calls": calls,
        "openapi_client": openapi_client,
        "mcp_client": mcp_client,
    }


def _hdrs() -> dict[str, str]:
    return {"X-Tenant-Id": str(TENANT), "X-Workspace-Id": str(WORKSPACE)}


# ── OpenAPI roundtrip ──────────────────────────────────────────────────────


async def test_openapi_tool_roundtrip() -> None:
    captured: dict[str, Any] = {}

    def _handler(req: httpx.Request) -> httpx.Response:
        captured["method"] = req.method
        captured["url"] = str(req.url)
        captured["query"] = dict(req.url.params)
        captured["headers"] = dict(req.headers)
        captured["body"] = json.loads(req.content) if req.content else None
        return httpx.Response(
            200,
            json={"id": 1, "name": "Widget"},
        )

    openapi_client = _client_with_handler(_handler)
    mcp_client = _client_with_handler(_handler)
    app, _ctx = _build_app(openapi_client, mcp_client)

    spec = {
        "servers": [{"url": "http://upstream.test"}],
        "paths": {
            "/widgets/{id}": {
                "get": {"operationId": "getWidget"},
            }
        },
    }
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        resp = await client.post(
            "/v1/tools",
            headers=_hdrs(),
            json={
                "name": "widgets",
                "description": "",
                "protocol": "openapi",
                "spec": spec,
            },
        )
        assert resp.status_code == 201

        resp = await client.post(
            "/v1/tools/widgets/invoke",
            headers=_hdrs(),
            json={
                "arguments": {
                    "__operation_id": "getWidget",
                    "path": {"id": "42"},
                    "query": {"expand": "true"},
                }
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["result"] == {"id": 1, "name": "Widget"}

    assert captured["method"] == "GET"
    assert "/widgets/42" in captured["url"]
    assert captured["query"] == {"expand": "true"}
    assert captured["body"] is None  # GET has no body


# ── MCP roundtrip ──────────────────────────────────────────────────────────


async def test_mcp_tool_roundtrip() -> None:
    captured: dict[str, Any] = {}

    def _handler(req: httpx.Request) -> httpx.Response:
        captured["method"] = req.method
        captured["url"] = str(req.url)
        captured["body"] = json.loads(req.content)
        captured["headers"] = dict(req.headers)
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": captured.get("body", {}).get("id", 1),
                "result": {"content": [{"type": "text", "text": "ok"}]},
            },
        )

    openapi_client = _client_with_handler(_handler)
    mcp_client = _client_with_handler(_handler)
    app, _ctx = _build_app(openapi_client, mcp_client)

    spec = {"server_url": "http://upstream.test/mcp", "mcp_tool_name": "fetch"}
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        resp = await client.post(
            "/v1/tools",
            headers=_hdrs(),
            json={
                "name": "mcptool",
                "description": "",
                "protocol": "mcp",
                "spec": spec,
            },
        )
        assert resp.status_code == 201

        resp = await client.post(
            "/v1/tools/mcptool/invoke",
            headers=_hdrs(),
            json={"arguments": {"url": "https://x.example"}},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["result"] == {"content": [{"type": "text", "text": "ok"}]}

    assert captured["method"] == "POST"
    assert captured["url"] == "http://upstream.test/mcp"
    envelope = captured["body"]
    assert envelope["jsonrpc"] == "2.0"
    assert envelope["method"] == "tools/call"
    assert envelope["params"]["name"] == "fetch"
    assert envelope["params"]["arguments"] == {"url": "https://x.example"}
    assert "text/event-stream" in captured["headers"]["accept"]


async def test_mcp_tool_sse_response() -> None:
    """Server pushes SSE; adapter must parse the last data: line."""
    captured: dict[str, Any] = {}

    def _handler(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.content)
        sse = (
            'data: {"jsonrpc":"2.0","id":1,"result":{"progress":0.5}}\n\n'
            'data: {"jsonrpc":"2.0","id":1,"result":{"final":true}}\n\n'
        )
        return httpx.Response(
            200, text=sse, headers={"content-type": "text/event-stream"}
        )

    openapi_client = _client_with_handler(_handler)
    mcp_client = _client_with_handler(_handler)
    app, _ctx = _build_app(openapi_client, mcp_client)

    spec = {"server_url": "http://upstream.test/mcp", "mcp_tool_name": "fetch"}
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        resp = await client.post(
            "/v1/tools",
            headers=_hdrs(),
            json={
                "name": "mcptool",
                "description": "",
                "protocol": "mcp",
                "spec": spec,
            },
        )
        assert resp.status_code == 201

        resp = await client.post(
            "/v1/tools/mcptool/invoke",
            headers=_hdrs(),
            json={"arguments": {}},
        )
        assert resp.status_code == 200
        body = resp.json()
        # The last SSE data: line carries {"final": true}.
        assert body["result"] == {"final": True}
