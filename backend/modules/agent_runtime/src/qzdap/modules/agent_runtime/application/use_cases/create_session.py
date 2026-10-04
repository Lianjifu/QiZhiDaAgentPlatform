"""Use case: create a new session against an agent.

Multi-tenancy:
  - `tenant_id` and `workspace_id` come from the verified JWT (already
    cross-checked against `X-Tenant-Id`/`X-Workspace-Id` by TenantGuard /
    WorkspaceGuard middleware).

Emits `SessionOpened` on success. Persistence is left to the adapter —
this use case only stages the aggregate.
"""

from __future__ import annotations

from uuid import uuid4

from qzdap_schema.ids import (
    AgentId,
    SessionId,
    TenantId,
    UserId,
    WorkspaceId,
)

from qzdap.modules.agent_runtime.application.ports import (
    EventPublisher,
    SessionRepository,
)
from qzdap.modules.agent_runtime.domain import Session


class CreateSessionUseCase:
    def __init__(self, sessions: SessionRepository, events: EventPublisher) -> None:
        self._sessions = sessions
        self._events = events

    async def execute(
        self,
        *,
        tenant_id: TenantId,
        workspace_id: WorkspaceId,
        owner_id: UserId,
        agent_id: AgentId,
        agent_version: str,
        metadata: dict | None = None,
    ) -> Session:
        session = Session.create(
            id=SessionId(uuid4()),
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            owner_id=owner_id,
            agent_id=agent_id,
            agent_version=agent_version,
            metadata=metadata,
        )
        await self._sessions.add(session)
        await self._events.publish(
            session.raise_opened_event(),
            tenant_id=tenant_id,
            workspace_id=workspace_id,
        )
        return session
