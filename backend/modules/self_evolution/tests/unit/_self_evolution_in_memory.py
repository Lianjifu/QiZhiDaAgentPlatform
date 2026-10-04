"""In-memory fakes for the self-evolution application ports.

Implements ``EvolutionCandidateRepository`` + ``ClockPort`` +
``IdGeneratorPort`` + ``EvolutionEventPublisher``. Mirrors the
``_governance_in_memory`` helper so unit tests can swap the wiring
without spinning up a database.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from qzdap.modules.self_evolution.application.ports import (
    ClockPort,
    EvolutionCandidateRepository,
    EvolutionEventPublisher,
    IdGeneratorPort,
)
from qzdap.modules.self_evolution.domain.entities import EvolveCandidate
from qzdap.modules.self_evolution.domain.value_objects import (
    EvolveStatus,
    is_terminal,
)

# ── ClockPort / IdGeneratorPort ────────────────────────────────────────────


@dataclass(slots=True)
class FixedClock(ClockPort):
    fixed_now: datetime = field(
        default_factory=lambda: datetime(2026, 1, 1, tzinfo=UTC)
    )

    def now(self) -> datetime:
        return self.fixed_now

    def advance(self, *, seconds: int = 0, minutes: int = 0, hours: int = 0) -> None:
        self.fixed_now = self.fixed_now + timedelta(
            seconds=seconds, minutes=minutes, hours=hours
        )


@dataclass(slots=True)
class Uuid4IdGenerator(IdGeneratorPort):
    def new_id(self) -> UUID:
        return uuid4()


# ── Event publisher (captures topics for assertions) ───────────────────────


@dataclass(slots=True)
class CapturingEventPublisher(EvolutionEventPublisher):
    events: list[tuple[str, dict[str, Any]]] = field(default_factory=list)

    async def publish(self, topic: str, payload: dict[str, Any]) -> None:
        self.events.append((topic, dict(payload)))


# ── EvolutionCandidateRepository ────────────────────────────────────────────


@dataclass(slots=True)
class InMemoryEvolutionCandidateRepository(EvolutionCandidateRepository):
    rows: dict[UUID, EvolveCandidate] = field(default_factory=dict)

    async def add(self, candidate: EvolveCandidate) -> None:
        self.rows[UUID(str(candidate.id))] = candidate

    async def get(
        self, *, tenant_id: UUID, candidate_id: UUID
    ) -> EvolveCandidate | None:
        row = self.rows.get(candidate_id)
        if row is None or row.tenant_id != tenant_id:
            return None
        return row

    async def update(self, candidate: EvolveCandidate) -> None:
        self.rows[UUID(str(candidate.id))] = candidate

    async def list_pending(
        self, *, tenant_id: UUID, now: datetime, limit: int = 200
    ) -> list[EvolveCandidate]:
        out: list[EvolveCandidate] = []
        for c in sorted(self.rows.values(), key=lambda x: x.created_at):
            if c.tenant_id != tenant_id:
                continue
            if is_terminal(c.status):
                continue
            if c.expires_at <= now:
                continue
            out.append(c)
            if len(out) >= limit:
                break
        return out

    async def list_by_status(
        self,
        *,
        tenant_id: UUID,
        status: EvolveStatus,
        limit: int = 100,
    ) -> list[EvolveCandidate]:
        out: list[EvolveCandidate] = []
        for c in sorted(self.rows.values(), key=lambda x: x.created_at, reverse=True):
            if c.tenant_id != tenant_id or c.status is not status:
                continue
            out.append(c)
            if len(out) >= limit:
                break
        return out


__all__ = [
    "CapturingEventPublisher",
    "FixedClock",
    "InMemoryEvolutionCandidateRepository",
    "Uuid4IdGenerator",
]
