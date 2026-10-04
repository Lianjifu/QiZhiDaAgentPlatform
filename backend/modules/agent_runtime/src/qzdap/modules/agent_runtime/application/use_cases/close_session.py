"""Use case: close an existing session.

Idempotency: a second `close()` on the same session raises
`SessionClosedError` (mapped to 410). The use case treats that as a
no-op success so a retry from a chatty client doesn't 500.
"""

from __future__ import annotations

from uuid import UUID

from qzdap.modules.agent_runtime.application.ports import (
    EventPublisher,
    SessionRepository,
)
from qzdap.modules.agent_runtime.domain.errors import (
    SessionClosedError,
    SessionNotFound,
)


class CloseSessionUseCase:
    def __init__(self, sessions: SessionRepository, events: EventPublisher) -> None:
        self._sessions = sessions
        self._events = events

    async def execute(self, *, tenant_id: UUID, session_id: UUID) -> None:
        existing = await self._sessions.get(session_id)
        if existing is None or existing.tenant_id != tenant_id:
            raise SessionNotFound(f"session {session_id} not found")
        try:
            closed = existing.close()
        except SessionClosedError:
            return  # idempotent
        await self._sessions.update(closed)
        await self._events.publish(
            closed.raise_closed_event(),
            tenant_id=tenant_id,
            workspace_id=closed.workspace_id,
        )
