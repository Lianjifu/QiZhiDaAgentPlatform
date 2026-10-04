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
    TurnORM,
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
        wait_status=getattr(o, "wait_status", None) or "idle",
    )


def turn_orm_to_domain(o: TurnORM) -> Turn:
    return Turn(
        id=TurnId(o.id),
        tenant_id=TenantId(o.tenant_id),
        workspace_id=WorkspaceId(o.workspace_id),
        session_id=SessionId(o.session_id),
        user_input=o.user_input,
        status=TurnStatus(o.status),
        started_at=o.started_at,
        finished_at=o.finished_at,
        final_response=o.final_response,
        input_tokens=o.input_tokens,
        output_tokens=o.output_tokens,
        error_code=o.error_code,
    )
