"""Self-evolution application ports — Repository / Clock / Publisher Protocols."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol, runtime_checkable
from uuid import UUID

from qzdap_schema.ids import (
    EvolveCandidateId,
    TenantId,
)

from qzdap.modules.self_evolution.domain.entities import EvolveCandidate
from qzdap.modules.self_evolution.domain.value_objects import EvolveStatus


@runtime_checkable
class EvolutionCandidateRepository(Protocol):
    async def add(self, candidate: EvolveCandidate) -> None: ...

    async def get(
        self, *, tenant_id: TenantId, candidate_id: EvolveCandidateId
    ) -> EvolveCandidate | None: ...

    async def update(self, candidate: EvolveCandidate) -> None: ...

    async def list_pending(
        self, *, tenant_id: TenantId, now: datetime, limit: int = 200
    ) -> list[EvolveCandidate]: ...

    async def list_by_status(
        self,
        *,
        tenant_id: TenantId,
        status: EvolveStatus,
        limit: int = 100,
    ) -> list[EvolveCandidate]: ...


@runtime_checkable
class EvolutionEventPublisher(Protocol):
    """Mirrors the kernel EventBus port, narrowed to evolution topics."""

    async def publish(self, topic: str, payload: dict[str, Any]) -> None: ...


@runtime_checkable
class ClockPort(Protocol):
    def now(self) -> datetime: ...


@runtime_checkable
class IdGeneratorPort(Protocol):
    def new_id(self) -> UUID: ...


__all__ = [
    "ClockPort",
    "EvolutionCandidateRepository",
    "EvolutionEventPublisher",
    "IdGeneratorPort",
]
