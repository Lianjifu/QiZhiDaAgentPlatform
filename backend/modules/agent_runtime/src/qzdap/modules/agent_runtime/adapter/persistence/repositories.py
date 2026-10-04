"""SQLAlchemy repository implementations of the application ports.

PK-only lookups additionally verify `tenant_id` against the value bound
via `bind_tenant_to_session` — defense in depth on top of the auto-filter
installed by `qzdap_persistence.tenant_guard.install_tenant_loader`.
"""

from __future__ import annotations

from uuid import UUID

from qzdap_persistence.tenant_guard import current_tenant_id
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from qzdap.modules.agent_runtime.adapter.persistence.mappers import (
    session_orm_to_domain,
    turn_orm_to_domain,
)
from qzdap.modules.agent_runtime.adapter.persistence.models import (
    SessionORM,
    TurnORM,
)
from qzdap.modules.agent_runtime.application.ports import (
    SessionRepository,
    TurnRepository,
)
from qzdap.modules.agent_runtime.domain import Session, Turn


def _cross_tenant(o: object) -> bool:
    """True if the loaded ORM row's `tenant_id` doesn't match the
    session-bound tenant. Used to silently None-out PK-only lookups that
    would otherwise leak cross-tenant rows before the route-level check."""
    bound = current_tenant_id()
    if bound is None:
        return False
    return getattr(o, "tenant_id", None) != bound


class SqlSessionRepository(SessionRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def add(self, session: Session) -> None:
        self._s.add(
            SessionORM(
                id=session.id,
                tenant_id=session.tenant_id,
                workspace_id=session.workspace_id,
                owner_id=session.owner_id,
                agent_id=session.agent_id,
                agent_version=session.agent_version,
                status=session.status.value,
                created_at=session.created_at,
                closed_at=session.closed_at,
                metadata_=session.metadata,
                graph_state=dict(session.graph_state or {}),
                wait_status=session.wait_status or "idle",
            )
        )

    async def update(self, session: Session) -> None:
        o = await self._s.get(SessionORM, session.id)
        if o is None or _cross_tenant(o):
            return
        o.status = session.status.value
        o.closed_at = session.closed_at
        o.metadata_ = session.metadata
        o.graph_state = dict(session.graph_state or {})
        o.wait_status = session.wait_status or "idle"

    async def get(self, session_id: UUID) -> Session | None:
        o = await self._s.get(SessionORM, session_id)
        if o is None or _cross_tenant(o):
            return None
        return session_orm_to_domain(o)

    async def list_for_owner(
        self, owner_id: UUID, *, limit: int = 50, offset: int = 0
    ) -> list[Session]:
        q = (
            select(SessionORM)
            .where(SessionORM.owner_id == owner_id)
            .order_by(SessionORM.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        rows = (await self._s.execute(q)).scalars().all()
        return [session_orm_to_domain(o) for o in rows]


class SqlTurnRepository(TurnRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def add(self, turn: Turn) -> None:
        # `add` is called twice per turn: once when the turn starts (status=
        # running) and again when it finishes (succeeded/failed). The second
        # call must update the existing row in place — emitting a second
        # INSERT with the same PK violates the primary key. The repository
        # contract is "always insert-or-update by id"; we route through the
        # session's identity-map and patch fields if the row is already
        # tracked.
        o = await self._s.get(TurnORM, turn.id)
        if o is None:
            self._s.add(
                TurnORM(
                    id=turn.id,
                    tenant_id=turn.tenant_id,
                    workspace_id=turn.workspace_id,
                    session_id=turn.session_id,
                    user_input=turn.user_input,
                    status=turn.status.value,
                    started_at=turn.started_at,
                    finished_at=turn.finished_at,
                    final_response=turn.final_response,
                    input_tokens=turn.input_tokens,
                    output_tokens=turn.output_tokens,
                    error_code=turn.error_code,
                )
            )
            return
        o.status = turn.status.value
        o.finished_at = turn.finished_at
        o.final_response = turn.final_response
        o.input_tokens = turn.input_tokens
        o.output_tokens = turn.output_tokens
        o.error_code = turn.error_code

    async def get(self, turn_id: UUID) -> Turn | None:
        o = await self._s.get(TurnORM, turn_id)
        if o is None or _cross_tenant(o):
            return None
        return turn_orm_to_domain(o)
