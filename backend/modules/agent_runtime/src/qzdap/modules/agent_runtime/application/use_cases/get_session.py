"""Use case: load a session by id, scoped to the caller's tenant.

The TenantScopedMixin auto-filter handles list queries, but PK lookups
need the explicit `tenant_id` check here — defense in depth.
"""

from __future__ import annotations

from uuid import UUID

from qzdap.modules.agent_runtime.application.ports import SessionRepository
from qzdap.modules.agent_runtime.domain import Session
from qzdap.modules.agent_runtime.domain.errors import SessionNotFound


class GetSessionUseCase:
    def __init__(self, sessions: SessionRepository) -> None:
        self._sessions = sessions

    async def execute(self, *, tenant_id: UUID, session_id: UUID) -> Session:
        s = await self._sessions.get(session_id)
        if s is None or s.tenant_id != tenant_id:
            raise SessionNotFound(f"session {session_id} not found")
        return s
