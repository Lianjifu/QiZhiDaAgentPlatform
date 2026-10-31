"""Application-layer ports (interfaces) for the tool module.

The adapter package implements these; use cases depend ONLY on ports.
Three runtime ports (`CustomInvokerPort`, `OpenAPIRuntime`, `MCPRuntime`)
are `Protocol` types — adapters inject `httpx.AsyncClient` and a secrets
resolver at the composition root.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Protocol

from qzdap.modules.tool.domain import (
    AuthConfig,
    SpecOperation,
    Tool,
    ToolCall,
)
from qzdap_kernel.events import DomainEvent
from qzdap_kernel.ids import TenantId, ToolCallId, ToolId, TurnId, UserId, WorkspaceId


class ToolRepository(ABC):
    @abstractmethod
    async def add(self, tool: Tool) -> None: ...
    @abstractmethod
    async def get(self, tool_id: ToolId) -> Tool | None: ...
    @abstractmethod
    async def get_by_name(self, *, tenant_id: TenantId, name: str) -> Tool | None: ...
    @abstractmethod
    async def list(
        self,
        *,
        tenant_id: TenantId,
        enabled: bool | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Tool]: ...
    @abstractmethod
    async def update(self, tool: Tool) -> None: ...
    @abstractmethod
    async def delete(self, tool_id: ToolId) -> None: ...


class ToolCallRepository(ABC):
    @abstractmethod
    async def add(self, call: ToolCall) -> None: ...
    @abstractmethod
    async def get(self, call_id: ToolCallId) -> ToolCall | None: ...


class ToolExecutionPort(Protocol):
    """**`tool_executions` 的窄端口** ✓（幂等的唯一权威 ✓ —— Agent 方案 §5.3.2 ✓）。

    ⚠️ **实现在会话域** ✓（`tool_executions.turn_id` 外键指向 `session_turns` ✓
    —— 表归会话域 ✓）—— 工具模块只**声明要什么** ✓（不引框架 ✓ 不跨域写表 ✓）。
    """

    async def begin(
        self,
        *,
        idempotency_key: str,
        request_hash: str,
        tool_call_id: str,
        turn_id: TurnId,
        tenant_id: TenantId,
        workspace_id: WorkspaceId,
    ) -> ToolExecutionClaim:
        """**占一次执行权** ✓。

        ⚠️ **抢到就返回 ``claimed=True``** ✓；**抢不到就返回既有行** ✓
        （冲突读回 ✓ —— 由调用方判断「同参复用」还是「异参拒绝」✓）。
        """
        ...

    async def finish(
        self,
        *,
        idempotency_key: str,
        status: str,
        result_ref: str | None = None,
    ) -> None:
        """**收尾** ✓（状态 ✓ + 结果指针 ✓）。"""
        ...


@dataclass(frozen=True, slots=True)
class ToolExecutionClaim:
    """**一次幂等占位的结果** ✓。"""

    #: 本次调用**抢到了执行权**吗 ✓。
    claimed: bool
    #: 既有行的状态 ✓（`pending` / `running` / `succeeded` / `failed` / `timeout` ✓）。
    status: str = "pending"
    #: 既有行的参数指纹 ✓（与本次算的不一致 → **拒绝** ✓）。
    request_hash: str = ""
    #: 既有行的结果指针 ✓（`tool_calls.id` 的字符串 ✓ —— `tool_calls.result` 才是正文 ✓）。
    result_ref: str | None = None
    #: 既有行的工具调用 id ✓。
    tool_call_id: str = ""


class EventPublisher(ABC):
    """Wraps the messaging bus for application-layer emission.

    The use case passes a `DomainEvent`; the publisher wraps it into an
    `EventEnvelope` with the request's tenant/workspace/trace scope."""

    @abstractmethod
    async def publish(
        self,
        event: DomainEvent,
        *,
        tenant_id: TenantId,
        workspace_id: WorkspaceId | None,
        trace_id: str | None = None,
    ) -> None: ...


# ── Runtime ports (Protocols) ──────────────────────────────────────


class CustomInvokerPort(Protocol):
    """In-process tool registry: name → async callable.

    Built-in tools (web_search / http_fetch / echo / reverse / clock) receive
    `tenant_id` / `workspace_id` / `call_id` / `actor_id` so they can audit-log
    egress and scope behaviour per workspace. Tenant-scope arguments are
    passed via kwargs so the public `arguments` dict stays user-controlled.
    """

    async def invoke(
        self,
        *,
        name: str,
        arguments: dict,
        tenant_id: TenantId,
        workspace_id: WorkspaceId | None,
        call_id: ToolCallId,
        actor_id: UserId,
    ) -> dict: ...


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
