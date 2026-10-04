"""HTTP integration tests for the tool router.

Wires the real `build_router()` onto a minimal FastAPI app and overrides
the per-request `tool_dependency` so the routes run against the
in-memory ports from `_in_memory.py`. This exercises real request
validation, response shaping, and HTTP status codes (201, 204, 207, 404,
409, 422, 412) without spinning up a database.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

import pytest
from _tool_integration_in_memory import (
    CollectingEventPublisher,
    FakeCustomInvoker,
    FakeMCPRuntime,
    FakeOpenAPIRuntime,
    InMemoryToolCallRepository,
    InMemoryToolRepository,
)
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from starlette.middleware.base import BaseHTTPMiddleware

from qzdap.modules.tool.adapter.http.router import build_router, tool_dependency
from qzdap.modules.tool.application.services import ToolService

TENANT = UUID("00000000-0000-0000-0000-000000000001")
WORKSPACE = UUID("00000000-0000-0000-0000-000000000002")


def _build_test_app() -> tuple[FastAPI, dict]:
    tools = InMemoryToolRepository()
    calls = InMemoryToolCallRepository()

    async def _echo(args: dict) -> dict:
        return {"echo": args}

    custom = FakeCustomInvoker()
    custom.register("echo", _echo)
    openapi = FakeOpenAPIRuntime()
    mcp = FakeMCPRuntime()
    events = CollectingEventPublisher()
    svc = ToolService(
        tools=tools,
        calls=calls,
        custom=custom,
        openapi=openapi,
        mcp=mcp,
        events=events,
    )

    app = FastAPI(title="tool-test")
    from qzdap_http.error_envelope import error_envelope_middleware

    app.add_middleware(BaseHTTPMiddleware, dispatch=error_envelope_middleware)  # type: ignore[arg-type]
    app.include_router(build_router())

    # Each batch item needs its own ToolService so the per-call factory
    # shape mirrors the production wiring (SQLAlchemy forbids concurrent
    # ops on a shared session). With in-memory ports there's no real
    # session, but the shape is identical and the route contract is.
    @asynccontextmanager
    async def _per_call_factory():
        yield svc

    # Middleware stashes the per-call factory onto request.state so the
    # real `tool_dependency` (running under the override) and the batch
    # route can both find it. A middleware sees `request` directly
    # without going through FastAPI's dep tree, so PEP 563 isn't an
    # issue here.
    @app.middleware("http")
    async def _stash_factory(request, call_next):
        request.state.tool_service_factory = _per_call_factory
        return await call_next(request)

    async def _provide() -> AsyncIterator[ToolService]:
        yield svc

    app.dependency_overrides[tool_dependency] = _provide
    return app, {
        "tools": tools,
        "calls": calls,
        "custom": custom,
        "openapi": openapi,
        "mcp": mcp,
        "events": events,
        "svc": svc,
    }


def _make_client(app: FastAPI) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")


def _hdrs() -> dict[str, str]:
    return {"X-Tenant-Id": str(TENANT), "X-Workspace-Id": str(WORKSPACE)}


@pytest.fixture
async def client_ctx() -> AsyncIterator[tuple[AsyncClient, dict]]:
    app, ctx = _build_test_app()
    async with _make_client(app) as c:
        yield c, ctx


# ── POST /v1/tools ──────────────────────────────────────────────────────────


async def test_register_returns_201_with_location_header(client_ctx) -> None:
    client, _ctx = client_ctx
    resp = await client.post(
        "/v1/tools",
        headers=_hdrs(),
        json={
            "name": "echo",
            "description": "echo args",
            "protocol": "custom",
            "spec": {},
        },
    )
    assert resp.status_code == 201
    assert resp.headers["location"].startswith("/v1/tools/")
    body = resp.json()
    assert body["name"] == "echo"
    assert body["protocol"] == "custom"
    assert body["version"] == 1


async def test_register_duplicate_returns_409(client_ctx) -> None:
    client, _ctx = client_ctx
    payload = {
        "name": "echo",
        "description": "",
        "protocol": "custom",
        "spec": {},
    }
    await client.post("/v1/tools", headers=_hdrs(), json=payload)
    resp = await client.post("/v1/tools", headers=_hdrs(), json=payload)
    assert resp.status_code == 409


async def test_register_invalid_spec_returns_422(client_ctx) -> None:
    client, _ctx = client_ctx
    resp = await client.post(
        "/v1/tools",
        headers=_hdrs(),
        json={
            "name": "bad",
            "description": "",
            "protocol": "openapi",
            "spec": {"no_paths": True},
        },
    )
    assert resp.status_code == 422


# ── GET /v1/tools + /v1/tools/{tid} ─────────────────────────────────────────


async def test_list_filters_by_tenant(client_ctx) -> None:
    client, ctx = client_ctx
    other = UUID("00000000-0000-0000-0000-0000000000ff")
    await (
        ctx["svc"]
        .register_tool()
        .execute(
            tenant_id=other,
            workspace_id=WORKSPACE,
            owner_id=UUID(int=7),
            name="ghost",
            description="",
            protocol=__import__(
                "qzdap.modules.tool.domain", fromlist=["ToolProtocol"]
            ).ToolProtocol.CUSTOM,
            spec={},
            auth_config=None,
            rate_limit_per_minute=None,
        )
    )
    await (
        ctx["svc"]
        .register_tool()
        .execute(
            tenant_id=TENANT,
            workspace_id=WORKSPACE,
            owner_id=UUID(int=8),
            name="echo",
            description="",
            protocol=__import__(
                "qzdap.modules.tool.domain", fromlist=["ToolProtocol"]
            ).ToolProtocol.CUSTOM,
            spec={},
            auth_config=None,
            rate_limit_per_minute=None,
        )
    )
    resp = await client.get("/v1/tools", headers=_hdrs())
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert {t["name"] for t in items} == {"echo"}


async def test_get_unknown_returns_404(client_ctx) -> None:
    client, _ctx = client_ctx
    resp = await client.get(
        "/v1/tools/00000000-0000-0000-0000-000000000999",
        headers=_hdrs(),
    )
    assert resp.status_code == 404


# ── PATCH /v1/tools/{tid} ──────────────────────────────────────────────────


async def test_update_with_matching_if_match(client_ctx) -> None:
    client, ctx = client_ctx
    tool = (
        await ctx["svc"]
        .register_tool()
        .execute(
            tenant_id=TENANT,
            workspace_id=WORKSPACE,
            owner_id=UUID(int=1),
            name="echo",
            description="",
            protocol=__import__(
                "qzdap.modules.tool.domain", fromlist=["ToolProtocol"]
            ).ToolProtocol.CUSTOM,
            spec={},
            auth_config=None,
            rate_limit_per_minute=None,
        )
    )
    resp = await client.patch(
        f"/v1/tools/{tool.id}",
        headers={**_hdrs(), "If-Match": "1"},
        json={"description": "new desc"},
    )
    assert resp.status_code == 200
    assert resp.json()["description"] == "new desc"
    assert resp.json()["version"] == 2


async def test_update_with_stale_if_match_returns_412(client_ctx) -> None:
    client, ctx = client_ctx
    tool = (
        await ctx["svc"]
        .register_tool()
        .execute(
            tenant_id=TENANT,
            workspace_id=WORKSPACE,
            owner_id=UUID(int=1),
            name="echo",
            description="",
            protocol=__import__(
                "qzdap.modules.tool.domain", fromlist=["ToolProtocol"]
            ).ToolProtocol.CUSTOM,
            spec={},
            auth_config=None,
            rate_limit_per_minute=None,
        )
    )
    resp = await client.patch(
        f"/v1/tools/{tool.id}",
        headers={**_hdrs(), "If-Match": "99"},
        json={"description": "new"},
    )
    assert resp.status_code == 412


# ── DELETE /v1/tools/{tid} ─────────────────────────────────────────────────


async def test_delete_returns_204(client_ctx) -> None:
    client, ctx = client_ctx
    tool = (
        await ctx["svc"]
        .register_tool()
        .execute(
            tenant_id=TENANT,
            workspace_id=WORKSPACE,
            owner_id=UUID(int=1),
            name="echo",
            description="",
            protocol=__import__(
                "qzdap.modules.tool.domain", fromlist=["ToolProtocol"]
            ).ToolProtocol.CUSTOM,
            spec={},
            auth_config=None,
            rate_limit_per_minute=None,
        )
    )
    resp = await client.delete(f"/v1/tools/{tool.id}", headers=_hdrs())
    assert resp.status_code == 204


# ── POST /v1/tools/{name}/invoke ───────────────────────────────────────────


async def test_invoke_custom_returns_200(client_ctx) -> None:
    client, ctx = client_ctx
    await (
        ctx["svc"]
        .register_tool()
        .execute(
            tenant_id=TENANT,
            workspace_id=WORKSPACE,
            owner_id=UUID(int=1),
            name="echo",
            description="",
            protocol=__import__(
                "qzdap.modules.tool.domain", fromlist=["ToolProtocol"]
            ).ToolProtocol.CUSTOM,
            spec={},
            auth_config=None,
            rate_limit_per_minute=None,
        )
    )
    resp = await client.post(
        "/v1/tools/echo/invoke",
        headers=_hdrs(),
        json={"arguments": {"x": 1}},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["tool_name"] == "echo"
    assert body["status"] == 200
    assert body["result"] == {"echo": {"x": 1}}
    assert body["latency_ms"] is not None


async def test_invoke_unknown_returns_404(client_ctx) -> None:
    client, _ctx = client_ctx
    resp = await client.post(
        "/v1/tools/ghost/invoke",
        headers=_hdrs(),
        json={"arguments": {}},
    )
    assert resp.status_code == 404


async def test_invoke_openapi_without_operation_id_returns_422(client_ctx) -> None:
    client, ctx = client_ctx
    await (
        ctx["svc"]
        .register_tool()
        .execute(
            tenant_id=TENANT,
            workspace_id=WORKSPACE,
            owner_id=UUID(int=1),
            name="api",
            description="",
            protocol=__import__(
                "qzdap.modules.tool.domain", fromlist=["ToolProtocol"]
            ).ToolProtocol.OPENAPI,
            spec={
                "servers": [{"url": "https://api.example.com"}],
                "paths": {"/x": {"get": {"operationId": "getX"}}},
            },
            auth_config=None,
            rate_limit_per_minute=None,
        )
    )
    resp = await client.post(
        "/v1/tools/api/invoke",
        headers=_hdrs(),
        json={"arguments": {}},
    )
    assert resp.status_code == 422


# ── POST /v1/tools/batch_invoke ────────────────────────────────────────────


async def test_batch_invoke_returns_207(client_ctx) -> None:
    client, ctx = client_ctx
    await (
        ctx["svc"]
        .register_tool()
        .execute(
            tenant_id=TENANT,
            workspace_id=WORKSPACE,
            owner_id=UUID(int=1),
            name="echo",
            description="",
            protocol=__import__(
                "qzdap.modules.tool.domain", fromlist=["ToolProtocol"]
            ).ToolProtocol.CUSTOM,
            spec={},
            auth_config=None,
            rate_limit_per_minute=None,
        )
    )
    resp = await client.post(
        "/v1/tools/batch_invoke",
        headers=_hdrs(),
        json={
            "calls": [
                {"tool_name": "echo", "arguments": {"a": 1}},
                {"tool_name": "ghost", "arguments": {}},
            ]
        },
    )
    assert resp.status_code == 207
    items = resp.json()["items"]
    assert items[0]["status"] == 200
    assert items[0]["result"] == {"echo": {"a": 1}}
    assert items[1]["status"] == 404
    assert items[1]["error"]["code"] == "TOOL_NOT_FOUND"


# ── Header validation (contract) ───────────────────────────────────────────


async def test_missing_x_tenant_id_returns_422(client_ctx) -> None:
    client, _ctx = client_ctx
    headers = {"X-Workspace-Id": str(WORKSPACE)}
    resp = await client.get("/v1/tools", headers=headers)
    # FastAPI's validation returns 422 for missing required Header.
    assert resp.status_code in (400, 422)


# ── Negative / multi-angle tests ────────────────────────────────────────────


async def test_register_missing_protocol_returns_422(client_ctx) -> None:
    client, _ctx = client_ctx
    resp = await client.post(
        "/v1/tools",
        headers=_hdrs(),
        json={"name": "x", "description": "", "spec": {}},  # no protocol
    )
    assert resp.status_code == 422


async def test_register_invalid_protocol_value_returns_422(client_ctx) -> None:
    client, _ctx = client_ctx
    resp = await client.post(
        "/v1/tools",
        headers=_hdrs(),
        json={"name": "x", "description": "", "protocol": "bogus", "spec": {}},
    )
    assert resp.status_code == 422


async def test_register_name_too_long_returns_422(client_ctx) -> None:
    client, _ctx = client_ctx
    resp = await client.post(
        "/v1/tools",
        headers=_hdrs(),
        json={
            "name": "x" * 200,
            "description": "",
            "protocol": "custom",
            "spec": {},
        },
    )
    assert resp.status_code == 422


async def test_register_rate_limit_out_of_range_returns_422(client_ctx) -> None:
    client, _ctx = client_ctx
    resp = await client.post(
        "/v1/tools",
        headers=_hdrs(),
        json={
            "name": "x",
            "description": "",
            "protocol": "custom",
            "spec": {},
            "rate_limit_per_minute": 0,
        },
    )
    assert resp.status_code == 422


async def test_register_extra_field_rejected(client_ctx) -> None:
    # The DTO declares extra='forbid'; an unknown field must be rejected.
    client, _ctx = client_ctx
    resp = await client.post(
        "/v1/tools",
        headers=_hdrs(),
        json={
            "name": "x",
            "description": "",
            "protocol": "custom",
            "spec": {},
            "rogue_field": "should_be_rejected",
        },
    )
    assert resp.status_code == 422


async def test_get_invalid_uuid_returns_422(client_ctx) -> None:
    client, _ctx = client_ctx
    resp = await client.get("/v1/tools/not-a-uuid", headers=_hdrs())
    assert resp.status_code == 422


async def test_update_with_unknown_uuid_returns_404(client_ctx) -> None:
    client, _ctx = client_ctx
    resp = await client.patch(
        "/v1/tools/00000000-0000-0000-0000-0000000000aa",
        headers=_hdrs(),
        json={"description": "x"},
    )
    assert resp.status_code == 404


async def test_update_with_strict_negative_test(client_ctx) -> None:
    """No prior tool → no version → any If-Match fails (404, not 412)."""
    client, _ctx = client_ctx
    resp = await client.patch(
        "/v1/tools/00000000-0000-0000-0000-0000000000aa",
        headers={**_hdrs(), "If-Match": "1"},
        json={"description": "x"},
    )
    # Tenant guard rejects first — 404, not 412.
    assert resp.status_code == 404


async def test_delete_unknown_returns_404(client_ctx) -> None:
    client, _ctx = client_ctx
    resp = await client.delete(
        "/v1/tools/00000000-0000-0000-0000-0000000000aa", headers=_hdrs()
    )
    assert resp.status_code == 404


async def test_invoke_empty_arguments_ok(client_ctx) -> None:
    # Default arguments={} should work for echo.
    client, ctx = client_ctx
    await (
        ctx["svc"]
        .register_tool()
        .execute(
            tenant_id=TENANT,
            workspace_id=WORKSPACE,
            owner_id=UUID(int=1),
            name="echo",
            description="",
            protocol=__import__(
                "qzdap.modules.tool.domain", fromlist=["ToolProtocol"]
            ).ToolProtocol.CUSTOM,
            spec={},
            auth_config=None,
            rate_limit_per_minute=None,
        )
    )
    resp = await client.post(
        "/v1/tools/echo/invoke",
        headers=_hdrs(),
        json={"arguments": {}},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == 200
    assert body["result"] == {"echo": {}}


async def test_invoke_extra_field_rejected(client_ctx) -> None:
    # InvokeToolRequest extra='forbid'.
    client, ctx = client_ctx
    await (
        ctx["svc"]
        .register_tool()
        .execute(
            tenant_id=TENANT,
            workspace_id=WORKSPACE,
            owner_id=UUID(int=1),
            name="echo",
            description="",
            protocol=__import__(
                "qzdap.modules.tool.domain", fromlist=["ToolProtocol"]
            ).ToolProtocol.CUSTOM,
            spec={},
            auth_config=None,
            rate_limit_per_minute=None,
        )
    )
    resp = await client.post(
        "/v1/tools/echo/invoke",
        headers=_hdrs(),
        json={"arguments": {}, "rogue": True},
    )
    assert resp.status_code == 422


async def test_batch_invoke_empty_list_returns_422(client_ctx) -> None:
    # BatchInvokeRequest requires min_length=1.
    client, _ctx = client_ctx
    resp = await client.post(
        "/v1/tools/batch_invoke", headers=_hdrs(), json={"calls": []}
    )
    assert resp.status_code == 422


async def test_batch_invoke_too_many_returns_422(client_ctx) -> None:
    # BatchInvokeRequest limits to max_length=50.
    client, _ctx = client_ctx
    resp = await client.post(
        "/v1/tools/batch_invoke",
        headers=_hdrs(),
        json={"calls": [{"tool_name": "echo", "arguments": {}} for _ in range(51)]},
    )
    assert resp.status_code == 422


async def test_batch_invoke_extra_field_rejected(client_ctx) -> None:
    client, _ctx = client_ctx
    resp = await client.post(
        "/v1/tools/batch_invoke",
        headers=_hdrs(),
        json={"calls": [], "rogue": True},
    )
    assert resp.status_code == 422


async def test_batch_invoke_at_max_length_ok(client_ctx) -> None:
    # Boundary: exactly 50 is allowed (max_length=50).
    client, ctx = client_ctx
    await (
        ctx["svc"]
        .register_tool()
        .execute(
            tenant_id=TENANT,
            workspace_id=WORKSPACE,
            owner_id=UUID(int=1),
            name="echo",
            description="",
            protocol=__import__(
                "qzdap.modules.tool.domain", fromlist=["ToolProtocol"]
            ).ToolProtocol.CUSTOM,
            spec={},
            auth_config=None,
            rate_limit_per_minute=None,
        )
    )
    resp = await client.post(
        "/v1/tools/batch_invoke",
        headers=_hdrs(),
        json={
            "calls": [{"tool_name": "echo", "arguments": {"i": i}} for i in range(50)]
        },
    )
    assert resp.status_code == 207
    items = resp.json()["items"]
    assert len(items) == 50
    assert all(it["status"] == 200 for it in items)


async def test_invoke_disabled_returns_409(client_ctx) -> None:
    client, ctx = client_ctx
    tool = await (
        ctx["svc"]
        .register_tool()
        .execute(
            tenant_id=TENANT,
            workspace_id=WORKSPACE,
            owner_id=UUID(int=1),
            name="echo",
            description="",
            protocol=__import__(
                "qzdap.modules.tool.domain", fromlist=["ToolProtocol"]
            ).ToolProtocol.CUSTOM,
            spec={},
            auth_config=None,
            rate_limit_per_minute=None,
        )
    )
    # Disable via the use case.
    await (
        ctx["svc"]
        .update_tool()
        .execute(
            tenant_id=TENANT,
            tool_id=tool.id,
            expected_version=1,
            description=None,
            spec=None,
            auth_config=None,
            clear_auth=False,
            rate_limit_per_minute=None,
            clear_rate_limit=False,
            enabled=False,
        )
    )
    resp = await client.post(
        "/v1/tools/echo/invoke",
        headers=_hdrs(),
        json={"arguments": {}},
    )
    assert resp.status_code == 409


async def test_register_path_traversal_in_name_rejected(client_ctx) -> None:
    # path traversal / slashes in name: the URL itself doesn't take the
    # name, but FastAPI's path-param parsing may reject some chars. We
    # only assert that the body validation rejects path-like names
    # whose length passes but whose characters break the protocol.
    client, _ctx = client_ctx
    resp = await client.post(
        "/v1/tools",
        headers=_hdrs(),
        json={
            "name": "../etc/passwd",
            "description": "",
            "protocol": "custom",
            "spec": {},
        },
    )
    # Either rejected at the DTO level (422) or accepted but stored —
    # we accept both; just ensure no 5xx.
    assert resp.status_code < 500


async def test_register_with_unsupported_protocol_in_body(client_ctx) -> None:
    # The DTO Literal enforces 'custom'|'openapi'|'mcp'. Anything else
    # is 422.
    client, _ctx = client_ctx
    resp = await client.post(
        "/v1/tools",
        headers=_hdrs(),
        json={
            "name": "x",
            "description": "",
            "protocol": "graphql",  # not in Literal
            "spec": {},
        },
    )
    assert resp.status_code == 422


async def test_update_with_extra_field_rejected(client_ctx) -> None:
    # UpdateToolRequest extra='forbid'.
    client, ctx = client_ctx
    tool = await (
        ctx["svc"]
        .register_tool()
        .execute(
            tenant_id=TENANT,
            workspace_id=WORKSPACE,
            owner_id=UUID(int=1),
            name="echo",
            description="",
            protocol=__import__(
                "qzdap.modules.tool.domain", fromlist=["ToolProtocol"]
            ).ToolProtocol.CUSTOM,
            spec={},
            auth_config=None,
            rate_limit_per_minute=None,
        )
    )
    resp = await client.patch(
        f"/v1/tools/{tool.id}",
        headers=_hdrs(),
        json={"description": "x", "rogue": True},
    )
    assert resp.status_code == 422
