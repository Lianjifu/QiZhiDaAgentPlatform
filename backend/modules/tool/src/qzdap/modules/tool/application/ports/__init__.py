"""Application-layer ports (interfaces) for the tool module.

The adapter package implements these; use cases depend ONLY on ports.
Three runtime ports (`CustomInvokerPort`, `OpenAPIRuntime`, `MCPRuntime`)
are `Protocol` types — adapters inject `httpx.AsyncClient` and a secrets
resolver at the composition root.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Protocol
from uuid import UUID

from qzdap_kernel.events import DomainEvent

from qzdap.modules.tool.domain import (
    AuthConfig,
    SpecOperation,
    Tool,
    ToolCall,
)


class ToolRepository(ABC):
    @abstractmethod
    async def add(self, tool: Tool) -> None: ...
    @abstractmethod
    async def get(self, tool_id: UUID) -> Tool | None: ...
    @abstractmethod
    async def get_by_name(self, *, tenant_id: UUID, name: str) -> Tool | None: ...
    @abstractmethod
    async def list(
        self,
        *,
        tenant_id: UUID,
        enabled: bool | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Tool]: ...
    @abstractmethod
    async def update(self, tool: Tool) -> None: ...
    @abstractmethod
    async def delete(self, tool_id: UUID) -> None: ...


class ToolCallRepository(ABC):
    @abstractmethod
    async def add(self, call: ToolCall) -> None: ...
    @abstractmethod
    async def get(self, call_id: UUID) -> ToolCall | None: ...


class EventPublisher(ABC):
    """Wraps the messaging bus for application-layer emission.

    The use case passes a `DomainEvent`; the publisher wraps it into an
    `EventEnvelope` with the request's tenant/workspace/trace scope."""

    @abstractmethod
    async def publish(
        self,
        event: DomainEvent,
        *,
        tenant_id: UUID,
        workspace_id: UUID | None,
        trace_id: str | None = None,
    ) -> None: ...


# ── Runtime ports (Protocols) ──────────────────────────────────────


class CustomInvokerPort(Protocol):
    """In-process tool registry: name → async callable(arguments: dict) -> dict."""

    async def invoke(self, *, name: str, arguments: dict) -> dict: ...


class OpenAPIRuntime(Protocol):
    async def invoke(
        self,
        *,
        base_url: str,
        operation: SpecOperation,
        auth: AuthConfig | None,
        arguments: dict,
        timeout: float,
    ) -> dict: ...


class MCPRuntime(Protocol):
    async def list_tools(
        self, *, server_url: str, auth: AuthConfig | None, timeout: float = 10.0
    ) -> list[dict]: ...

    async def call_tool(
        self,
        *,
        server_url: str,
        tool_name: str,
        arguments: dict,
        auth: AuthConfig | None,
        timeout: float,
    ) -> dict: ...
