"""SQL repository implementation for EvolveCandidate."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from qzdap.modules.self_evolution.adapter.persistence.mappers import (
    candidate_to_domain,
    candidate_to_orm,
)
from qzdap.modules.self_evolution.adapter.persistence.models import (
    EvolveCandidateORM,
)
from qzdap.modules.self_evolution.application.ports import (
    EvolutionCandidateRepository,
)
from qzdap.modules.self_evolution.domain.entities import EvolveCandidate
from qzdap.modules.self_evolution.domain.value_objects import EvolveStatus


class SqlEvolutionCandidateRepository(EvolutionCandidateRepository):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def add(self, candidate: EvolveCandidate) -> None:
        async with self._sf() as session:
            session.add(candidate_to_orm(candidate))
            await session.commit()

    async def get(
        self, *, tenant_id: UUID, candidate_id: UUID
    ) -> EvolveCandidate | None:
        async with self._sf() as session:
            row = await session.get(EvolveCandidateORM, candidate_id)
            if row is None or row.tenant_id != tenant_id:
                return None
            return candidate_to_domain(row)

    async def update(self, candidate: EvolveCandidate) -> None:
        async with self._sf() as session:
            stmt = (
                update(EvolveCandidateORM)
                .where(EvolveCandidateORM.id == UUID(str(candidate.id)))
                .where(EvolveCandidateORM.tenant_id == UUID(str(candidate.tenant_id)))
                .values(
                    status=candidate.status.value,
                    approver_id=UUID(str(candidate.approver_id))
                    if candidate.approver_id
                    else None,
                    reviewed_at=candidate.reviewed_at,
                    applied_at=candidate.applied_at,
                    payload=dict(candidate.payload),
                    expires_at=candidate.expires_at,
                )
            )
            await session.execute(stmt)
            await session.commit()

    async def list_pending(
        self, *, tenant_id: UUID, now: datetime, limit: int = 200
    ) -> list[EvolveCandidate]:
        async with self._sf() as session:
            stmt = (
                select(EvolveCandidateORM)
                .where(EvolveCandidateORM.tenant_id == tenant_id)
                .where(EvolveCandidateORM.status == EvolveStatus.PENDING.value)
                .where(EvolveCandidateORM.expires_at > now)
                .order_by(EvolveCandidateORM.created_at.asc())
                .limit(limit)
            )
            rows = (await session.execute(stmt)).scalars().all()
            return [candidate_to_domain(r) for r in rows]

    async def list_by_status(
        self,
        *,
        tenant_id: UUID,
        status: EvolveStatus,
        limit: int = 100,
    ) -> list[EvolveCandidate]:
        async with self._sf() as session:
            stmt = (
                select(EvolveCandidateORM)
                .where(EvolveCandidateORM.tenant_id == tenant_id)
                .where(EvolveCandidateORM.status == status.value)
                .order_by(EvolveCandidateORM.created_at.desc())
                .limit(limit)
            )
            rows = (await session.execute(stmt)).scalars().all()
            return [candidate_to_domain(r) for r in rows]


__all__ = ["SqlEvolutionCandidateRepository"]
