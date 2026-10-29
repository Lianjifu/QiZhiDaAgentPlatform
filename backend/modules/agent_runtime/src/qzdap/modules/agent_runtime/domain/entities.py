"""Session and Turn aggregates.

Both are tenant-scoped, mutable-on-method-call (frozen dataclass + factory
+ state-transition methods), and emit domain events via the `raise_*_event`
convention. Persistence is the adapter's responsibility — domain stays
framework-free.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Self

from qzdap_agent_runtime.session.state import SessionStatus
from qzdap_schema.ids import (
    AgentId,
    SessionId,
    TenantId,
    TurnId,
    UserId,
    WorkspaceId,
)

from qzdap.modules.agent_runtime.domain.errors import SessionClosedError
from qzdap.modules.agent_runtime.domain.events import (
    SessionClosed,
    SessionOpened,
    TurnCompleted,
    TurnFailed,
    TurnStarted,
)

# ⚠️ **会话状态是唯一的一份** —— 定义在契约层（Session 方案 §4.1），
# 这里只是**转出** ✓（``domain/__init__.py`` 再导出给调用方）。
#
# 为什么收上去：这张表原先只有 `open` / `closed` 两个值，而
# `agent_sessions.status` 的 check constraint 有**五个**（`running` /
# `waiting_approval` / `cancelled` 从来没在领域层出现过 ✗）—— 领域枚举落后于
# 表约束 = 又一套真相 ✓。契约层的 `session/state.py` 同时给出**状态机**
# （合法转移 + 非法转移报错 ✓）。


class TurnStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    DENIED = "denied"


@dataclass(slots=True, frozen=True)
class Session:
    id: SessionId
    tenant_id: TenantId
    workspace_id: WorkspaceId
    owner_id: UserId
    agent_id: AgentId
    agent_version: str
    status: SessionStatus
    created_at: datetime
    closed_at: datetime | None = None
    metadata: dict = field(default_factory=dict)
    graph_state: dict = field(default_factory=dict)
    wait_status: str = "idle"

    @classmethod
    def create(
        cls,
        *,
        id: SessionId,
        tenant_id: TenantId,
        workspace_id: WorkspaceId,
        owner_id: UserId,
        agent_id: AgentId,
        agent_version: str,
        metadata: dict | None = None,
    ) -> Self:
        if not agent_version or len(agent_version) > 64:
            raise ValueError(
                f"invalid agent_version: {agent_version!r} (must be non-empty, <=64 chars)"
            )
        return cls(
            id=id,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            owner_id=owner_id,
            agent_id=agent_id,
            agent_version=agent_version,
            status=SessionStatus.OPEN,
            created_at=datetime.now(UTC),
            closed_at=None,
            metadata=dict(metadata or {}),
            graph_state={},
            wait_status="idle",
        )

    def close(self) -> Self:
        """Mark this session closed. Idempotent failure: a second `close()`
        raises `SessionClosedError` so we don't silently drop audit events."""
        if self.status is SessionStatus.CLOSED:
            raise SessionClosedError(
                f"session {self.id} already closed",
                code="SESSION_CLOSED",
            )
        return type(self)(
            id=self.id,
            tenant_id=self.tenant_id,
            workspace_id=self.workspace_id,
            owner_id=self.owner_id,
            agent_id=self.agent_id,
            agent_version=self.agent_version,
            status=SessionStatus.CLOSED,
            created_at=self.created_at,
            closed_at=datetime.now(UTC),
            metadata=dict(self.metadata),
            graph_state=dict(self.graph_state),
            wait_status=self.wait_status,
        )

    def with_runtime(
        self,
        *,
        metadata: dict | None = None,
        graph_state: dict | None = None,
        wait_status: str | None = None,
    ) -> Self:
        return type(self)(
            id=self.id,
            tenant_id=self.tenant_id,
            workspace_id=self.workspace_id,
            owner_id=self.owner_id,
            agent_id=self.agent_id,
            agent_version=self.agent_version,
            status=self.status,
            created_at=self.created_at,
            closed_at=self.closed_at,
            metadata=dict(metadata if metadata is not None else self.metadata),
            graph_state=dict(graph_state if graph_state is not None else self.graph_state),
            wait_status=wait_status if wait_status is not None else self.wait_status,
        )

    def raise_opened_event(self) -> SessionOpened:
        return SessionOpened(
            session_id=self.id,
            tenant_id=self.tenant_id,
            workspace_id=self.workspace_id,
            owner_id=self.owner_id,
            agent_id=self.agent_id,
            agent_version=self.agent_version,
        )

    def raise_closed_event(self) -> SessionClosed:
        return SessionClosed(session_id=self.id, tenant_id=self.tenant_id)


@dataclass(slots=True, frozen=True)
class Turn:
    id: TurnId
    tenant_id: TenantId
    workspace_id: WorkspaceId
    session_id: SessionId
    user_input: str
    status: TurnStatus
    started_at: datetime
    finished_at: datetime | None = None
    final_response: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None
    error_code: str | None = None

    @classmethod
    def create(
        cls,
        *,
        id: TurnId,
        tenant_id: TenantId,
        workspace_id: WorkspaceId,
        session_id: SessionId,
        user_input: str,
    ) -> Self:
        if not user_input or not user_input.strip():
            raise ValueError("user_input must be a non-empty string")
        return cls(
            id=id,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            session_id=session_id,
            user_input=user_input,
            status=TurnStatus.RUNNING,
            started_at=datetime.now(UTC),
            finished_at=None,
            final_response=None,
            input_tokens=None,
            output_tokens=None,
            cost_usd=None,
            error_code=None,
        )

    def succeed(
        self,
        *,
        finished_at: datetime | None = None,
        final_response: str | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        cost_usd: float | None = None,
    ) -> Self:
        return type(self)(
            id=self.id,
            tenant_id=self.tenant_id,
            workspace_id=self.workspace_id,
            session_id=self.session_id,
            user_input=self.user_input,
            status=TurnStatus.SUCCEEDED,
            started_at=self.started_at,
            finished_at=finished_at or datetime.now(UTC),
            final_response=final_response,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
            error_code=None,
        )

    def fail(
        self,
        *,
        finished_at: datetime | None = None,
        error_code: str,
        error_message: str | None = None,
    ) -> Self:
        return type(self)(
            id=self.id,
            tenant_id=self.tenant_id,
            workspace_id=self.workspace_id,
            session_id=self.session_id,
            user_input=self.user_input,
            status=TurnStatus.FAILED,
            started_at=self.started_at,
            finished_at=finished_at or datetime.now(UTC),
            final_response=error_message,
            input_tokens=None,
            output_tokens=None,
            cost_usd=None,
            error_code=error_code,
        )

    def raise_started_event(self) -> TurnStarted:
        return TurnStarted(
            turn_id=self.id,
            session_id=self.session_id,
            tenant_id=self.tenant_id,
            workspace_id=self.workspace_id,
        )

    def raise_completed_event(self, *, final_message_length: int) -> TurnCompleted:
        return TurnCompleted(
            turn_id=self.id,
            session_id=self.session_id,
            tenant_id=self.tenant_id,
            workspace_id=self.workspace_id,
            input_tokens=self.input_tokens or 0,
            output_tokens=self.output_tokens or 0,
            final_message_length=final_message_length,
        )

    def raise_failed_event(self, *, message: str = "") -> TurnFailed:
        return TurnFailed(
            turn_id=self.id,
            session_id=self.session_id,
            tenant_id=self.tenant_id,
            code=self.error_code or "TURN_FAILED",
            message=message or (self.final_response or ""),
        )
