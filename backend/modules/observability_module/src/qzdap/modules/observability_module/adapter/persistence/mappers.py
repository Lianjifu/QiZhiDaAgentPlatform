"""Domain ↔ ORM mappers for the observability_module.

Pure functions; SQL repositories call these from inside the session.

Notes:

- ``CostRecord.amount_usd`` is reconstructed from the SQL NUMERIC(12, 6)
  column using ``Decimal(str(value))`` so we don't lose precision via
  ``float(...)``.
- ``metadata_`` is the SQLAlchemy attribute name (the column name is
  ``metadata`` — a reserved word in PostgreSQL only in DDL contexts;
  the column is rename-mapped).
"""

from __future__ import annotations

from decimal import Decimal

from qzdap_schema.ids import (
    CostRecordId,
    RunRecordId,
    TenantId,
    UserId,
    WorkspaceId,
)

from qzdap.modules.observability_module.adapter.persistence.models import (
    CostRecordORM,
    RunRecordORM,
)
from qzdap.modules.observability_module.domain.entities import (
    CostRecord,
    RunRecord,
)
from qzdap.modules.observability_module.domain.value_objects import (
    CostType,
    RunStatus,
    RunType,
)


def _to_decimal(value: object) -> Decimal:
    """Reconstruct Decimal from a SQL NUMERIC column or string."""
    if isinstance(value, Decimal):
        return value
    if value is None:
        raise ValueError("CostRecord.amount_usd cannot be NULL")
    return Decimal(str(value))


# ── RunRecord ─────────────────────────────────────────────────────────────


def run_record_to_domain(row: RunRecordORM) -> RunRecord:
    return RunRecord(
        id=RunRecordId(row.id),
        tenant_id=TenantId(row.tenant_id),
        workspace_id=WorkspaceId(row.workspace_id),
        run_type=RunType(row.run_type),
        source_id=row.source_id,
        actor_id=UserId(row.actor_id) if row.actor_id else None,
        started_at=row.started_at,
        completed_at=row.completed_at,
        latency_ms=row.latency_ms,
        status=RunStatus(row.status),
        metadata=dict(row.metadata_ or {}),
        created_at=row.created_at,
    )


def run_record_to_orm(entity: RunRecord) -> RunRecordORM:
    return RunRecordORM(
        id=entity.id,
        tenant_id=entity.tenant_id,
        workspace_id=entity.workspace_id,
        run_type=entity.run_type.value,
        source_id=entity.source_id,
        actor_id=entity.actor_id,
        started_at=entity.started_at,
        completed_at=entity.completed_at,
        latency_ms=entity.latency_ms,
        status=entity.status.value,
        metadata_=dict(entity.metadata),
        created_at=entity.created_at,
    )


# ── CostRecord ────────────────────────────────────────────────────────────


def cost_record_to_domain(row: CostRecordORM) -> CostRecord:
    return CostRecord(
        id=CostRecordId(row.id),
        tenant_id=TenantId(row.tenant_id),
        workspace_id=WorkspaceId(row.workspace_id),
        run_id=RunRecordId(row.run_id),
        cost_type=CostType(row.cost_type),
        amount_usd=_to_decimal(row.amount_usd),
        quantity=row.quantity,
        unit=row.unit,
        currency=row.currency,
        model_id=row.model_id,
        metadata=dict(row.metadata_ or {}),
        created_at=row.created_at,
    )


def cost_record_to_orm(entity: CostRecord) -> CostRecordORM:
    return CostRecordORM(
        id=entity.id,
        tenant_id=entity.tenant_id,
        workspace_id=entity.workspace_id,
        run_id=entity.run_id,
        cost_type=entity.cost_type.value,
        amount_usd=entity.amount_usd,
        quantity=entity.quantity,
        unit=entity.unit,
        currency=entity.currency,
        model_id=entity.model_id,
        metadata_=dict(entity.metadata),
        created_at=entity.created_at,
    )


__all__ = [
    "cost_record_to_domain",
    "cost_record_to_orm",
    "run_record_to_domain",
    "run_record_to_orm",
]
