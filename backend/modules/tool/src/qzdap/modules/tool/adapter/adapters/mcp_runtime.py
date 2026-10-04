"""MCP runtime adapter — JSON-RPC 2.0 over HTTP, self-implemented.

No `mcp` / `fastmcp` dependency. Handles two response shapes per the
MCP spec:
  - `application/json` — synchronous JSON-RPC reply
  - `text/event-stream` — server pushes events; one `data: {...}` line per
    JSON-RPC reply.

The `tools/list` and `tools/call` methods are the only ones we expose —
just enough to satisfy doc 12 §P2's exit criterion. Stdio transport is
left for P10 deployment.
"""

from __future__ import annotations

import json
from itertools import count
from typing import Any

import httpx
from qzdap_vault.actor import ActorContext

from qzdap.modules.tool.adapter.adapters.openapi_runtime import (
    SecretsResolver,
    _adapter,
    _no_op_secrets_resolver,
)
from qzdap.modules.tool.domain import AuthConfig, AuthConfigType


def _parse_sse_jsonrpc(text: str) -> dict[str, Any]:
    """Pull the first `data: {...}` JSON-RPC envelope out of an SSE stream.

    Some MCP servers emit several events per request (e.g. progress + final).
    We take the *last* `data:` line as the final result; intermediate ones
    are ignored — orchestration-grade handling is P7."""
    last: dict[str, Any] | None = None
    for line in text.splitlines():
        if line.startswith("data:"):
            payload = line[len("data:") :].strip()
            if not payload:
                continue
            try:
                last = json.loads(payload)
            except json.JSONDecodeError:
                continue
    if last is None:
        raise httpx.HTTPError("MCP SSE stream had no data: line")
    if "error" in last:
        raise httpx.HTTPError(f"MCP server returned error: {last['error']}")
    if "result" not in last:
        raise httpx.HTTPError("MCP server returned no result")
    return last


class MCPRuntimeAdapter:
    def __init__(
        self,
        *,
        http: httpx.AsyncClient,
        secrets_resolver: SecretsResolver | None = None,
    ) -> None:
        self._http = http
        self._secrets = (
            _adapter(secrets_resolver)
            if secrets_resolver is not None
            else _no_op_secrets_resolver
        )

    async def list_tools(
        self,
        *,
        server_url: str,
        auth: AuthConfig | None,
        timeout: float = 10.0,
        actor: ActorContext | None = None,
    ) -> list[dict]:
        envelope = await self._rpc(
            server_url=server_url,
            method="tools/list",
            params={},
            auth=auth,
            timeout=timeout,
            request_id=next(_id),
            actor=actor,
        )
        result = envelope.get("result") or {}
        tools = result.get("tools") or []
        return list(tools)

    async def call_tool(
        self,
        *,
        server_url: str,
        tool_name: str,
        arguments: dict,
        auth: AuthConfig | None,
        timeout: float,
        actor: ActorContext | None = None,
    ) -> dict:
        envelope = await self._rpc(
            server_url=server_url,
            method="tools/call",
            params={"name": tool_name, "arguments": arguments},
            auth=auth,
            timeout=timeout,
            request_id=next(_id),
            actor=actor,
        )
        return envelope.get("result") or {}

    async def _rpc(
        self,
        *,
        server_url: str,
        method: str,
        params: dict,
        auth: AuthConfig | None,
        timeout: float,
        request_id: str | int,
        actor: ActorContext | None = None,
    ) -> dict[str, Any]:
        envelope = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params,
        }
        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if auth is not None:
            ctx = actor or ActorContext.anonymous(
                tenant_id=__import__("uuid").UUID(int=0)
            )
            headers.update(await self._inject_auth(auth, ctx))

        resp = await self._http.post(
            server_url, json=envelope, headers=headers, timeout=timeout
        )
        resp.raise_for_status()
        ctype = resp.headers.get("content-type", "")
        if ctype.startswith("text/event-stream"):
            return _parse_sse_jsonrpc(resp.text)
        body = resp.json()
        if isinstance(body, dict) and "error" in body:
            raise httpx.HTTPError(f"MCP server returned error: {body['error']}")
        return body

    async def _inject_auth(
        self, auth: AuthConfig, actor: ActorContext
    ) -> dict[str, str]:
        headers: dict[str, str] = {}
        if auth.type is AuthConfigType.NONE or not auth.secrets_ref:
            return headers
        secret = await self._secrets(auth.secrets_ref, actor)
        if auth.type is AuthConfigType.BEARER:
            token = secret.get("token") or secret.get("value", "")
            if token:
                headers["Authorization"] = f"Bearer {token}"
        elif auth.type is AuthConfigType.API_KEY:
            header_name = secret.get("header", "X-Api-Key")
            api_key = secret.get("api_key") or secret.get("value", "")
            if api_key:
                headers[header_name] = api_key
        elif auth.type is AuthConfigType.OAUTH2:
            token = secret.get("access_token") or secret.get("value", "")
            if token:
                headers["Authorization"] = f"Bearer {token}"
        return headers


# Module-shared monotonic counter. Each JSON-RPC request must carry a
# unique id so the upstream can correlate request → response. Reusing
# a per-call iterator would cause every request to ship id=1, which
# makes correlation impossible across pipelined calls.
_id = count(1)


__all__ = ["MCPRuntimeAdapter"]
