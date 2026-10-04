"""Self-evolution domain events."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4

from qzdap_kernel.events import DomainEvent
from qzdap_schema.ids import (
    EvolveCandidateId,
    TenantId,
    UserId,
)

from qzdap.modules.self_evolution.domain.value_objects import (
    EvolveKind,
    EvolveStatus,
)


@dataclass(slots=True, frozen=True)
class EvolutionCandidateCreated(DomainEvent):
    candidate_id: EvolveCandidateId
    tenant_id: TenantId
    kind: EvolveKind
    confidence: float
    occurred_at: datetime
    requester_id: UserId | None = None
    topic: str = "governance.evolution.candidate.created"
    event_id: UUID = field(default_factory=uuid4)


@dataclass(slots=True, frozen=True)
class EvolutionCandidateDecided(DomainEvent):
    candidate_id: EvolveCandidateId
    tenant_id: TenantId
    approver_id: UserId
    status: EvolveStatus
    occurred_at: datetime
    topic: str = "governance.evolution.candidate.decided"
    event_id: UUID = field(default_factory=uuid4)


@dataclass(slots=True, frozen=True)
class EvolutionCandidateApplied(DomainEvent):
    candidate_id: EvolveCandidateId
    tenant_id: TenantId
    kind: EvolveKind
    summary: dict[str, str]
    occurred_at: datetime
    topic: str = "governance.evolution.candidate.applied"
    event_id: UUID = field(default_factory=uuid4)


__all__ = [
    "EvolutionCandidateApplied",
    "EvolutionCandidateCreated",
    "EvolutionCandidateDecided",
]
