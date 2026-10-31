"""ORM ↔ domain mappers. Pure functions."""

from __future__ import annotations

from qzdap.modules.agent_runtime.adapter.persistence.models import (
    SessionORM,
    SessionTurnORM,
)
from qzdap.modules.agent_runtime.domain import Session, SessionStatus, Turn, TurnStatus
from qzdap_kernel.ids import (
    AgentId,
    SessionId,
    TenantId,
    TurnId,
    UserId,
    WorkspaceId,
)


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
        rolling_summary=str(getattr(o, "rolling_summary", None) or ""),
    )


def session_turn_orm_to_domain(o: SessionTurnORM) -> Turn:
    """新表 ``session_turns`` 的行 → ``Turn`` 领域实体 ✓。

    ⚠️ **状态直接用契约层那一份** ✓（2026-10-31 ✓ —— 与 ``SessionStatus``
    同一口径 ✓）：新表 ``session_turns.status`` 的六个值（``queued`` /
    ``running`` / ``waiting`` / ``succeeded`` / ``failed`` / ``cancelled`` ✓）
    与状态机**逐一对应** ✓ → **不需要有损映射** ✓（原先映射成 ``denied`` ✓
    → 「被取消的轮次」在任务卡上显示成「已拒绝」✗✗）。

    ⚠️ 新表**没有** ``final_response`` / token 数 ✗ —— 领域实体里留空 ✓
    （读它们的地方已经没有了 ✓；回复在**事件流**里 ✓）。
    """
    status = o.status
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
