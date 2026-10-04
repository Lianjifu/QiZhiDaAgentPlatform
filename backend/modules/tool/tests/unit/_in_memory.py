"""In-memory fakes for tool module unit tests."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID

from qzdap.modules.tool.adapter.adapters.openapi_runtime import SecretsResolver
from qzdap.modules.tool.application.ports import (
    CustomInvokerPort,
    EventPublisher,
    MCPRuntime,
    OpenAPIRuntime,
    ToolCallRepository,
    ToolRepository,
)
from qzdap.modules.tool.domain import (
    AuthConfig,
    SpecOperation,
    Tool,
    ToolCall,
)


class InMemoryToolRepository(ToolRepository):
    def __init__(self) -> None:
        self._by_id: dict[UUID, Tool] = {}

    async def add(self, tool: Tool) -> None:
        self._by_id[tool.id] = tool

    async def update(self, tool: Tool) -> None:
        self._by_id[tool.id] = tool

    async def delete(self, tool_id: UUID) -> None:
        self._by_id.pop(tool_id, None)

    async def get(self, tool_id: UUID) -> Tool | None:
        return self._by_id.get(tool_id)

    async def get_by_name(self, *, tenant_id: UUID, name: str) -> Tool | None:
        for t in self._by_id.values():
            if t.tenant_id == tenant_id and t.name == name:
                return t
        return None

    async def list(
        self,
        *,
        tenant_id: UUID,
        enabled: bool | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Tool]:
        items = [t for t in self._by_id.values() if t.tenant_id == tenant_id]
        if enabled is not None:
            items = [t for t in items if t.enabled == enabled]
        items.sort(key=lambda t: t.created_at, reverse=True)
        return items[offset : offset + limit]


class InMemoryToolCallRepository(ToolCallRepository):
    def __init__(self) -> None:
        self._by_id: dict[UUID, ToolCall] = {}

    async def add(self, call: ToolCall) -> None:
        self._by_id[call.id] = call

    async def get(self, call_id: UUID) -> ToolCall | None:
        return self._by_id.get(call_id)


class CollectingEventPublisher(EventPublisher):
    def __init__(self) -> None:
        self.published: list[tuple[Any, dict[str, Any]]] = []

    async def publish(
        self,
        event,
        *,
        tenant_id: UUID,
        workspace_id: UUID | None,
        trace_id: str | None = None,
    ) -> None:
        self.published.append(
            (event, {"tenant_id": tenant_id, "workspace_id": workspace_id})
        )


class FakeCustomInvoker(CustomInvokerPort):
    def __init__(
        self,
        registry: dict[str, Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]]
        | None = None,
    ) -> None:
        self._registry: dict[
            str, Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]
        ] = dict(registry or {})
        # Last call arguments received by invoke(); lets tests assert that
        # internal routing keys (`__operation_id`, `__foo`) are stripped.
        self.last_args: dict[str, Any] | None = None
        self.last_name: str | None = None

    def register(
        self,
        name: str,
        fn: Callable[[dict[str, Any]], Awaitable[dict[str, Any]]],
    ) -> None:
        self._registry[name] = fn

    async def invoke(self, *, name: str, arguments: dict) -> dict:
        self.last_name = name
        self.last_args = dict(arguments)
        if name not in self._registry:
            from qzdap.modules.tool.domain.errors import ToolNotFound

            raise ToolNotFound(f"custom tool {name!r} not registered")
        return dict(await self._registry[name](arguments))


class FakeOpenAPIRuntime(OpenAPIRuntime):
    """Captures invocations and returns a stubbed response."""

    def __init__(self, response: dict[str, Any] | None = None) -> None:
        self.invocations: list[dict[str, Any]] = []
        self.response = response or {"ok": True}
        self.raise_status: int | None = None

    async def invoke(
        self,
        *,
        base_url: str,
        operation: SpecOperation,
        auth: AuthConfig | None,
        arguments: dict,
        timeout: float,
    ) -> dict:
        self.invocations.append(
            {
                "base_url": base_url,
                "operation": operation,
                "auth": auth,
                "arguments": dict(arguments),
                "timeout": timeout,
            }
        )
        if self.raise_status is not None:
            import httpx

            resp = httpx.Response(self.raise_status, json={"error": "boom"})
            raise httpx.HTTPStatusError(
                "boom", request=httpx.Request("GET", "x"), response=resp
            )
        return self.response


class FakeMCPRuntime(MCPRuntime):
    def __init__(self) -> None:
        self.list_calls: list[dict[str, Any]] = []
        self.call_calls: list[dict[str, Any]] = []
        self.tools: list[dict[str, Any]] = []
        self.call_response: dict[str, Any] = {"ok": True}

    async def list_tools(
        self, *, server_url: str, auth: AuthConfig | None, timeout: float = 10.0
    ) -> list[dict]:
        self.list_calls.append(
            {"server_url": server_url, "auth": auth, "timeout": timeout}
        )
        return list(self.tools)

    async def call_tool(
        self,
        *,
        server_url: str,
        tool_name: str,
        arguments: dict,
        auth: AuthConfig | None,
        timeout: float,
    ) -> dict:
        self.call_calls.append(
            {
                "server_url": server_url,
                "tool_name": tool_name,
                "arguments": dict(arguments),
                "auth": auth,
                "timeout": timeout,
            }
        )
        return self.call_response


def noop_secrets_resolver(_ref: str) -> dict[str, str]:
    return {}


def make_secrets_resolver(
    mapping: dict[str, dict[str, str]] | None = None,
) -> SecretsResolver:
    async def _resolver(ref: str) -> dict[str, str]:
        return dict((mapping or {}).get(ref, {}))

    return _resolver


__all__ = [
    "CollectingEventPublisher",
    "FakeCustomInvoker",
    "FakeMCPRuntime",
    "FakeOpenAPIRuntime",
    "InMemoryToolCallRepository",
    "InMemoryToolRepository",
    "make_secrets_resolver",
    "noop_secrets_resolver",
]


# json imported to keep helpers above valid; silence unused warnings.
_ = json
