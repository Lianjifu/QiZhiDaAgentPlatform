"""Tests for MCPRuntimeAdapter JSON-RPC envelope + SSE fallback parsing."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from qzdap.modules.tool.adapter.adapters.mcp_runtime import (
    MCPRuntimeAdapter,
    _parse_sse_jsonrpc,
)
from qzdap.modules.tool.domain import AuthConfig, AuthConfigType


def _make_handler(responses: list[httpx.Response]) -> httpx.MockTransport:
    """Build a MockTransport that yields a new response per request."""
    state = {"count": 0}

    def _handler(req: httpx.Request) -> httpx.Response:
        i = state["count"]
        state["count"] += 1
        return responses[i]

    return httpx.MockTransport(_handler)


def _client(transport: httpx.MockTransport) -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url="https://mcp.example.com", transport=transport)


@pytest.mark.asyncio
async def test_tools_list_sends_json_rpc_envelope() -> None:
    captured: dict[str, Any] = {}

    def _handler(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.content)
        captured["headers"] = dict(req.headers)
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "result": {"tools": [{"name": "fetch"}, {"name": "search"}]},
            },
        )

    client = _client(_make_handler([httpx.Response(200)]))
    # Override transport by attaching mock
    client._transport = httpx.MockTransport(_handler)  # type: ignore[attr-defined]
    adapter = MCPRuntimeAdapter(http=client)

    tools = await adapter.list_tools(
        server_url="https://mcp.example.com/mcp", auth=None, timeout=5.0
    )
    assert tools == [{"name": "fetch"}, {"name": "search"}]
    assert captured["body"]["jsonrpc"] == "2.0"
    assert captured["body"]["method"] == "tools/list"
    assert captured["body"]["params"] == {}
    assert isinstance(captured["body"]["id"], int)
    assert captured["headers"]["content-type"] == "application/json"
    assert "text/event-stream" in captured["headers"]["accept"]


@pytest.mark.asyncio
async def test_tools_call_sends_arguments() -> None:
    captured: dict[str, Any] = {}

    def _handler(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.content)
        return httpx.Response(
            200, json={"jsonrpc": "2.0", "id": 1, "result": {"ok": True}}
        )

    client = _client(_make_handler([httpx.Response(200)]))
    client._transport = httpx.MockTransport(_handler)  # type: ignore[attr-defined]
    adapter = MCPRuntimeAdapter(http=client)

    result = await adapter.call_tool(
        server_url="https://mcp.example.com/mcp",
        tool_name="fetch",
        arguments={"url": "https://x"},
        auth=None,
        timeout=5.0,
    )
    assert result == {"ok": True}
    assert captured["body"]["method"] == "tools/call"
    assert captured["body"]["params"] == {
        "name": "fetch",
        "arguments": {"url": "https://x"},
    }


@pytest.mark.asyncio
async def test_sse_response_parses_last_data_line() -> None:
    sse_body = (
        "event: progress\n"
        'data: {"jsonrpc":"2.0","id":1,"result":null}\n\n'
        "event: final\n"
        'data: {"jsonrpc":"2.0","id":1,"result":{"final":true}}\n\n'
    )

    def _handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            text=sse_body,
            headers={"content-type": "text/event-stream"},
        )

    client = _client(_make_handler([httpx.Response(200)]))
    client._transport = httpx.MockTransport(_handler)  # type: ignore[attr-defined]
    adapter = MCPRuntimeAdapter(http=client)

    tools = await adapter.list_tools(
        server_url="https://mcp.example.com", auth=None, timeout=5.0
    )
    # list_tools → tools/list → result.tools → envelope result has no "tools" so []
    # The call_tool path with same envelope would yield {"final": True}.
    assert tools == []  # no "tools" key in last envelope → []


@pytest.mark.asyncio
async def test_sse_response_with_tools() -> None:
    sse_body = 'data: {"jsonrpc":"2.0","id":1,"result":{"tools":[{"name":"a"}]}}\n\n'

    def _handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, text=sse_body, headers={"content-type": "text/event-stream"}
        )

    client = _client(_make_handler([httpx.Response(200)]))
    client._transport = httpx.MockTransport(_handler)  # type: ignore[attr-defined]
    adapter = MCPRuntimeAdapter(http=client)

    tools = await adapter.list_tools(
        server_url="https://mcp.example.com", auth=None, timeout=5.0
    )
    assert tools == [{"name": "a"}]


@pytest.mark.asyncio
async def test_bearer_auth_injects_token() -> None:
    captured: dict[str, Any] = {}

    async def _resolver(ref: str, *, actor: Any = None) -> dict[str, str]:
        return {"token": "secret-tok"}

    def _handler(req: httpx.Request) -> httpx.Response:
        captured["auth"] = req.headers.get("authorization")
        return httpx.Response(
            200, json={"jsonrpc": "2.0", "id": 1, "result": {"tools": []}}
        )

    client = _client(_make_handler([httpx.Response(200)]))
    client._transport = httpx.MockTransport(_handler)  # type: ignore[attr-defined]
    adapter = MCPRuntimeAdapter(http=client, secrets_resolver=_resolver)

    await adapter.list_tools(
        server_url="https://mcp.example.com",
        auth=AuthConfig(type=AuthConfigType.BEARER, secrets_ref="r1"),
        timeout=5.0,
    )
    assert captured["auth"] == "Bearer secret-tok"


@pytest.mark.asyncio
async def test_http_error_envelope_raises() -> None:
    def _handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"jsonrpc": "2.0", "id": 1, "error": {"code": -32601}}
        )

    client = _client(_make_handler([httpx.Response(200)]))
    client._transport = httpx.MockTransport(_handler)  # type: ignore[attr-defined]
    adapter = MCPRuntimeAdapter(http=client)

    with pytest.raises(httpx.HTTPError):
        await adapter.list_tools(
            server_url="https://mcp.example.com", auth=None, timeout=5.0
        )


@pytest.mark.asyncio
async def test_timeout() -> None:
    def _handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("upstream dead")

    client = _client(_make_handler([httpx.Response(200)]))
    client._transport = httpx.MockTransport(_handler)  # type: ignore[attr-defined]
    adapter = MCPRuntimeAdapter(http=client)

    with pytest.raises(httpx.ConnectTimeout):
        await adapter.list_tools(
            server_url="https://mcp.example.com", auth=None, timeout=0.01
        )


class TestParseSSE:
    def test_single_data_line(self) -> None:
        text = 'data: {"jsonrpc":"2.0","id":1,"result":{"tools":[]}}\n\n'
        env = _parse_sse_jsonrpc(text)
        assert env["result"] == {"tools": []}

    def test_takes_last_data_line(self) -> None:
        text = (
            'data: {"jsonrpc":"2.0","id":1,"result":{"partial":1}}\n\n'
            'data: {"jsonrpc":"2.0","id":1,"result":{"final":2}}\n\n'
        )
        env = _parse_sse_jsonrpc(text)
        assert env["result"] == {"final": 2}

    def test_ignores_blank_data_lines(self) -> None:
        text = 'data:\n\ndata: {"jsonrpc":"2.0","id":1,"result":{"ok":1}}\n\n'
        env = _parse_sse_jsonrpc(text)
        assert env["result"] == {"ok": 1}

    def test_error_envelope_raises(self) -> None:
        text = 'data: {"jsonrpc":"2.0","id":1,"error":{"code":-32601}}\n\n'
        with pytest.raises(httpx.HTTPError):
            _parse_sse_jsonrpc(text)

    def test_no_data_raises(self) -> None:
        with pytest.raises(httpx.HTTPError):
            _parse_sse_jsonrpc("event: ping\n\n")

    def test_empty_stream_raises(self) -> None:
        with pytest.raises(httpx.HTTPError):
            _parse_sse_jsonrpc("")

    def test_only_garbage_raises(self) -> None:
        with pytest.raises(httpx.HTTPError):
            _parse_sse_jsonrpc("hello world\nrandom text\n")

    def test_malformed_json_data_lines_are_skipped(self) -> None:
        # Lines that fail to parse are skipped, not raised — the parser
        # recovers when a later valid data line shows up.
        text = (
            "data: {not-valid-json\n\n"
            'data: {"jsonrpc":"2.0","id":1,"result":{"ok":true}}\n\n'
        )
        env = _parse_sse_jsonrpc(text)
        assert env["result"] == {"ok": True}

    def test_envelope_without_result_or_error_raises(self) -> None:
        # A data: line with no result and no error key is malformed.
        text = 'data: {"jsonrpc":"2.0","id":1}\n\n'
        with pytest.raises(httpx.HTTPError):
            _parse_sse_jsonrpc(text)

    def test_comments_and_event_lines_ignored(self) -> None:
        # SSE permits comment lines (start with ':') and event: type lines;
        # both must be ignored.
        text = (
            ": this is a comment\n"
            "event: message\n"
            "id: 42\n"
            'data: {"jsonrpc":"2.0","id":1,"result":{"v":1}}\n\n'
        )
        env = _parse_sse_jsonrpc(text)
        assert env["result"] == {"v": 1}


class TestMCPRuntimeNegative:
    @pytest.mark.asyncio
    async def test_http_status_error_raises(self) -> None:
        # Upstream 500 → httpx.HTTPStatusError (the adapter does NOT swallow
        # transport errors).
        def _handler(req: httpx.Request) -> httpx.Response:
            return httpx.Response(500, text="upstream dead")

        client = _client(_make_handler([httpx.Response(500)]))
        client._transport = httpx.MockTransport(_handler)  # type: ignore[attr-defined]
        adapter = MCPRuntimeAdapter(http=client)

        with pytest.raises(httpx.HTTPStatusError):
            await adapter.list_tools(
                server_url="https://mcp.example.com", auth=None, timeout=5.0
            )

    @pytest.mark.asyncio
    async def test_http_404_raises(self) -> None:
        def _handler(req: httpx.Request) -> httpx.Response:
            return httpx.Response(404, text="not found")

        client = _client(_make_handler([httpx.Response(404)]))
        client._transport = httpx.MockTransport(_handler)  # type: ignore[attr-defined]
        adapter = MCPRuntimeAdapter(http=client)

        with pytest.raises(httpx.HTTPStatusError):
            await adapter.call_tool(
                server_url="https://mcp.example.com",
                tool_name="x",
                arguments={},
                auth=None,
                timeout=5.0,
            )

    @pytest.mark.asyncio
    async def test_json_rpc_error_envelope_raises(self) -> None:
        # Application/json response with a JSON-RPC error envelope must
        # be re-raised as httpx.HTTPError (the use case then maps to 502).
        def _handler(req: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "error": {"code": -32601, "message": "method not found"},
                },
            )

        client = _client(_make_handler([httpx.Response(200)]))
        client._transport = httpx.MockTransport(_handler)  # type: ignore[attr-defined]
        adapter = MCPRuntimeAdapter(http=client)

        with pytest.raises(httpx.HTTPError) as ei:
            await adapter.list_tools(
                server_url="https://mcp.example.com", auth=None, timeout=5.0
            )
        assert "method not found" in str(ei.value) or "error" in str(ei.value)

    @pytest.mark.asyncio
    async def test_sse_error_envelope_raises(self) -> None:
        # Same as above but for SSE responses.
        body = 'data: {"jsonrpc":"2.0","id":1,"error":{"code":-32602}}\n\n'

        def _handler(req: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200, text=body, headers={"content-type": "text/event-stream"}
            )

        client = _client(_make_handler([httpx.Response(200)]))
        client._transport = httpx.MockTransport(_handler)  # type: ignore[attr-defined]
        adapter = MCPRuntimeAdapter(http=client)

        with pytest.raises(httpx.HTTPError):
            await adapter.call_tool(
                server_url="https://mcp.example.com",
                tool_name="x",
                arguments={},
                auth=None,
                timeout=5.0,
            )

    @pytest.mark.asyncio
    async def test_sse_empty_stream_raises(self) -> None:
        def _handler(req: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200, text="", headers={"content-type": "text/event-stream"}
            )

        client = _client(_make_handler([httpx.Response(200)]))
        client._transport = httpx.MockTransport(_handler)  # type: ignore[attr-defined]
        adapter = MCPRuntimeAdapter(http=client)

        with pytest.raises(httpx.HTTPError):
            await adapter.list_tools(
                server_url="https://mcp.example.com", auth=None, timeout=5.0
            )

    @pytest.mark.asyncio
    async def test_json_rpc_request_includes_request_id(self) -> None:
        # Each call must include a unique request id; we capture two
        # consecutive calls and confirm the ids differ.
        captured: list[int] = []

        def _handler(req: httpx.Request) -> httpx.Response:
            body = json.loads(req.content)
            captured.append(int(body["id"]))
            return httpx.Response(
                200, json={"jsonrpc": "2.0", "id": body["id"], "result": {}}
            )

        client = _client(_make_handler([httpx.Response(200), httpx.Response(200)]))
        client._transport = httpx.MockTransport(_handler)  # type: ignore[attr-defined]
        adapter = MCPRuntimeAdapter(http=client)

        await adapter.list_tools(
            server_url="https://mcp.example.com", auth=None, timeout=5.0
        )
        await adapter.list_tools(
            server_url="https://mcp.example.com", auth=None, timeout=5.0
        )
        assert len(captured) == 2
        assert captured[0] != captured[1]

    @pytest.mark.asyncio
    async def test_call_tool_uses_tools_call_method(self) -> None:
        # Ensure that call_tool dispatches method='tools/call' (not list).
        captured: dict[str, Any] = {}

        def _handler(req: httpx.Request) -> httpx.Response:
            captured["body"] = json.loads(req.content)
            return httpx.Response(
                200, json={"jsonrpc": "2.0", "id": 1, "result": {"ok": 1}}
            )

        client = _client(_make_handler([httpx.Response(200)]))
        client._transport = httpx.MockTransport(_handler)  # type: ignore[attr-defined]
        adapter = MCPRuntimeAdapter(http=client)

        await adapter.call_tool(
            server_url="https://mcp.example.com",
            tool_name="x",
            arguments={"a": 1},
            auth=None,
            timeout=5.0,
        )
        assert captured["body"]["method"] == "tools/call"
        assert captured["body"]["params"] == {"name": "x", "arguments": {"a": 1}}

    @pytest.mark.asyncio
    async def test_no_auth_injects_no_auth_headers(self) -> None:
        # When auth is None the request must not contain an Authorization
        # or X-Api-Key header.
        captured: dict[str, Any] = {}

        def _handler(req: httpx.Request) -> httpx.Response:
            captured["headers"] = dict(req.headers)
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": {}})

        client = _client(_make_handler([httpx.Response(200)]))
        client._transport = httpx.MockTransport(_handler)  # type: ignore[attr-defined]
        adapter = MCPRuntimeAdapter(http=client)

        await adapter.list_tools(
            server_url="https://mcp.example.com", auth=None, timeout=5.0
        )
        assert "authorization" not in {k.lower() for k in captured["headers"]}

    @pytest.mark.asyncio
    async def test_bearer_with_empty_token_skips_header(self) -> None:
        # secrets_resolver returns no token → no Authorization header.
        captured: dict[str, Any] = {}

        async def _resolver(ref: str, *, actor: Any = None) -> dict[str, str]:
            return {}  # no token

        def _handler(req: httpx.Request) -> httpx.Response:
            captured["headers"] = dict(req.headers)
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": {}})

        client = _client(_make_handler([httpx.Response(200)]))
        client._transport = httpx.MockTransport(_handler)  # type: ignore[attr-defined]
        adapter = MCPRuntimeAdapter(http=client, secrets_resolver=_resolver)

        await adapter.list_tools(
            server_url="https://mcp.example.com",
            auth=AuthConfig(type=AuthConfigType.BEARER, secrets_ref="r1"),
            timeout=5.0,
        )
        assert "authorization" not in {k.lower() for k in captured["headers"]}

    @pytest.mark.asyncio
    async def test_api_key_uses_configured_header(self) -> None:
        # The configured X-Api-Key (default) header carries the api key.
        captured: dict[str, Any] = {}

        async def _resolver(ref: str, *, actor: Any = None) -> dict[str, str]:
            return {"api_key": "k-123", "header": "X-Api-Key"}

        def _handler(req: httpx.Request) -> httpx.Response:
            captured["headers"] = dict(req.headers)
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": {}})

        client = _client(_make_handler([httpx.Response(200)]))
        client._transport = httpx.MockTransport(_handler)  # type: ignore[attr-defined]
        adapter = MCPRuntimeAdapter(http=client, secrets_resolver=_resolver)

        await adapter.list_tools(
            server_url="https://mcp.example.com",
            auth=AuthConfig(type=AuthConfigType.API_KEY, secrets_ref="r1"),
            timeout=5.0,
        )
        assert captured["headers"]["x-api-key"] == "k-123"

    @pytest.mark.asyncio
    async def test_oauth2_uses_bearer_format(self) -> None:
        captured: dict[str, Any] = {}

        async def _resolver(ref: str, *, actor: Any = None) -> dict[str, str]:
            return {"access_token": "tok-456"}

        def _handler(req: httpx.Request) -> httpx.Response:
            captured["auth"] = req.headers.get("authorization")
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": {}})

        client = _client(_make_handler([httpx.Response(200)]))
        client._transport = httpx.MockTransport(_handler)  # type: ignore[attr-defined]
        adapter = MCPRuntimeAdapter(http=client, secrets_resolver=_resolver)

        await adapter.list_tools(
            server_url="https://mcp.example.com",
            auth=AuthConfig(type=AuthConfigType.OAUTH2, secrets_ref="r1"),
            timeout=5.0,
        )
        assert captured["auth"] == "Bearer tok-456"

    @pytest.mark.asyncio
    async def test_auth_with_no_secrets_ref_skips_header(self) -> None:
        # type=bearer but secrets_ref=None → no Authorization header
        # (rather than Authorization: 'Bearer ' with empty token).
        captured: dict[str, Any] = {}

        def _handler(req: httpx.Request) -> httpx.Response:
            captured["headers"] = dict(req.headers)
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": {}})

        client = _client(_make_handler([httpx.Response(200)]))
        client._transport = httpx.MockTransport(_handler)  # type: ignore[attr-defined]
        adapter = MCPRuntimeAdapter(http=client)

        await adapter.list_tools(
            server_url="https://mcp.example.com",
            auth=AuthConfig(type=AuthConfigType.BEARER, secrets_ref=None),
            timeout=5.0,
        )
        assert "authorization" not in {k.lower() for k in captured["headers"]}

    @pytest.mark.asyncio
    async def test_auth_none_with_secrets_ref_still_no_headers(self) -> None:
        # type=none → no headers regardless of secrets_ref.
        captured: dict[str, Any] = {}

        async def _resolver(ref: str, *, actor: Any = None) -> dict[str, str]:
            return {"token": "x"}

        def _handler(req: httpx.Request) -> httpx.Response:
            captured["headers"] = dict(req.headers)
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": {}})

        client = _client(_make_handler([httpx.Response(200)]))
        client._transport = httpx.MockTransport(_handler)  # type: ignore[attr-defined]
        adapter = MCPRuntimeAdapter(http=client, secrets_resolver=_resolver)

        await adapter.list_tools(
            server_url="https://mcp.example.com",
            auth=AuthConfig.none(),
            timeout=5.0,
        )
        assert "authorization" not in {k.lower() for k in captured["headers"]}
