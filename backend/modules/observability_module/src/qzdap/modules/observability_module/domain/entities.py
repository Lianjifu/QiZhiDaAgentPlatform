"""Observability domain entities.

Two aggregate roots:

- :class:`RunRecord` — a single business-action observation (turn, tool
  call, skill invocation, etc.).  Source-of-truth is the originating
  domain event; the row records ``source_id`` (the upstream entity id)
  for cross-reference.
- :class:`CostRecord` — a money line attached to a :class:`RunRecord`.
  One RunRecord may produce N CostRecords (e.g. an LLM invocation
  produces both ``LLM_INPUT`` and ``LLM_OUTPUT`` rows).

All entities are frozen dataclasses with ``slots=True``; mutation goes
through factory classmethods.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from qzdap_schema.ids import (
    CostRecordId,
    RunRecordId,
    TenantId,
    UserId,
    WorkspaceId,
)

from qzdap.modules.observability_module.domain.value_objects import (
    CostType,
    RunStatus,
    RunType,
)


def _utcnow() -> datetime:
    return datetime.now(UTC)


# ── RunRecord ────────────────────────────────────────────────────────────


@dataclass(slots=True, frozen=True)
class RunRecord:
    """A single observed business action.

    Created from an event-bus envelope; ``source_id`` is the upstream
    entity id (turn_id, tool_call_id, skill_invocation_id, etc.).
    """

    id: RunRecordId
    tenant_id: TenantId
    workspace_id: WorkspaceId
    run_type: RunType
    source_id: UUID | None
    actor_id: UserId | None
    started_at: datetime | None
    completed_at: datetime
    latency_ms: int | None
    status: RunStatus
    metadata: dict[str, Any]
    created_at: datetime

    @classmethod
    def from_event(
        cls,
        *,
        tenant_id: TenantId,
        workspace_id: WorkspaceId,
        run_type: RunType,
        source_id: UUID | None,
        completed_at: datetime,
        status: RunStatus,
        latency_ms: int | None = None,
        actor_id: UserId | None = None,
        started_at: datetime | None = None,
        metadata: dict[str, Any] | None = None,
        run_id: RunRecordId | None = None,
    ) -> RunRecord:
        ts = _utcnow()
        return cls(
            id=run_id or RunRecordId(uuid4()),
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            run_type=run_type,
            source_id=source_id,
            actor_id=actor_id,
            started_at=started_at,
            completed_at=completed_at,
            latency_ms=latency_ms,
            status=status,
            metadata=dict(metadata or {}),
            created_at=ts,
        )


# ── CostRecord ───────────────────────────────────────────────────────────


@dataclass(slots=True, frozen=True)
class CostRecord:
    """A money line attached to a :class:`RunRecord`.

    ``amount_usd`` is :class:`Decimal` with 6 fractional digits
    (matches the NUMERIC(12, 6) SQL column).  ``unit`` is the unit
    string for the quantity (``token`` / ``call`` / ``chunk`` / ``byte``).
    """

    id: CostRecordId
    tenant_id: TenantId
    workspace_id: WorkspaceId
    run_id: RunRecordId
    cost_type: CostType
    amount_usd: Decimal
    quantity: int | None
    unit: str
    currency: str
    model_id: str | None
    metadata: dict[str, Any]
    created_at: datetime

    @classmethod
    def create(
        cls,
        *,
        tenant_id: TenantId,
        workspace_id: WorkspaceId,
        run_id: RunRecordId,
        cost_type: CostType,
        amount_usd: Decimal,
        quantity: int | None = None,
        unit: str = "call",
        currency: str = "USD",
        model_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        cost_id: CostRecordId | None = None,
    ) -> CostRecord:
        if amount_usd < Decimal(0):
            raise ValueError("CostRecord.amount_usd must be >= 0")
        if not unit or len(unit) > 16:
            raise ValueError("CostRecord.unit must be 1..16 chars")
        if not currency or len(currency) > 8:
            raise ValueError("CostRecord.currency must be 1..8 chars")
        ts = _utcnow()
        return cls(
            id=cost_id or CostRecordId(uuid4()),
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            run_id=run_id,
            cost_type=cost_type,
            amount_usd=amount_usd,
            quantity=quantity,
            unit=unit,
            currency=currency,
            model_id=model_id,
            metadata=dict(metadata or {}),
            created_at=ts,
        )


__all__ = [
    "CostRecord",
    "RunRecord",
]
