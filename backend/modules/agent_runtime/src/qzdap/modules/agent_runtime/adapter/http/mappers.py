"""Domain ↔ DTO mappers."""

from __future__ import annotations

from qzdap.modules.agent_runtime.adapter.http.dto import (
    SessionResponse,
    TurnResponse,
)
from qzdap.modules.agent_runtime.domain import Session, Turn


def session_to_dto(s: Session) -> SessionResponse:
    return SessionResponse(
        id=s.id,
        tenant_id=s.tenant_id,
        workspace_id=s.workspace_id,
        owner_id=s.owner_id,
        agent_id=s.agent_id,
        agent_version=s.agent_version,
        status=s.status.value,
        created_at=s.created_at,
        closed_at=s.closed_at,
        metadata=dict(s.metadata or {}),
    )


def turn_to_dto(t: Turn) -> TurnResponse:
    return TurnResponse(
        id=t.id,
        session_id=t.session_id,
        status=t.status.value,
        started_at=t.started_at,
        finished_at=t.finished_at,
        final_response=t.final_response,
        input_tokens=t.input_tokens,
        output_tokens=t.output_tokens,
        error_code=t.error_code,
    )
