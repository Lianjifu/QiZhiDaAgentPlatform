"""ORM ↔ domain mappers. Pure functions."""

from __future__ import annotations

from qzdap_schema.ids import (
    AgentId,
    SessionId,
    TenantId,
    TurnId,
    UserId,
    WorkspaceId,
)

from qzdap.modules.agent_runtime.adapter.persistence.models import (
    SessionORM,
    SessionTurnORM,
)
from qzdap.modules.agent_runtime.domain import Session, SessionStatus, Turn, TurnStatus


def session_orm_to_domain(o: SessionORM) -> Session:
    return Session(
        id=SessionId(o.id),
        tenant_id=TenantId(o.tenant_id),
        workspace_id=WorkspaceId(o.workspace_id),
        owner_id=UserId(o.owner_id),
        agent_id=AgentId(o.agent_id),
        agent_version=o.agent_version,
        status=SessionStatus(o.status),
        created_at=o.created_at,
        closed_at=o.closed_at,
        metadata=dict(o.metadata_ or {}),
        graph_state=dict(getattr(o, "graph_state", None) or {}),
    )


def session_turn_orm_to_domain(o: SessionTurnORM) -> Turn:
    """新表 ``session_turns`` 的行 → ``Turn`` 领域实体 ✓。

    ⚠️ **状态映射**：新表的枚举比领域的多两个 ✓ ——
    ``waiting``（挂起等审批）→ ``running`` ✓（卡片另有「等你确认」分支 ✓）；
    ``cancelled``（被取消）→ ``denied`` ✓（领域里最接近的「没跑成」✓）。

    ⚠️ 新表**没有** ``final_response`` / token 数 ✗ —— 领域实体里留空 ✓
    （读它们的地方已经没有了 ✓；回复在**事件流**里 ✓）。
    """
    status = {
        "waiting": TurnStatus.RUNNING.value,
        "cancelled": TurnStatus.DENIED.value,
    }.get(o.status, o.status)
    return Turn(
        id=TurnId(o.id),
        tenant_id=TenantId(o.tenant_id),
        workspace_id=WorkspaceId(o.workspace_id),
        session_id=SessionId(o.session_id),
        user_input=o.user_input or "",
        status=TurnStatus(status),
        started_at=o.started_at,
        finished_at=o.finished_at,
        final_response="",
        input_tokens=None,
        output_tokens=None,
        error_code=o.error_code,
    )
