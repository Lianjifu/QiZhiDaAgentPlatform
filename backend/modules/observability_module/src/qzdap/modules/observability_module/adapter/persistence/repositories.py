"""Async-SQLAlchemy implementation of the observability_module ports.

- :class:`SqlRunRecordRepository` — ``run_records`` table
- :class:`SqlCostRecordRepository` — ``cost_records`` table

Both repositories accept an injected ``AsyncSession``.  Aggregations
use ``func.sum`` / ``group_by`` to keep the cost math in SQL.

The repositories deliberately do NOT publish events themselves; the
recorder subscriber pattern means event publication happens in
application code (use cases).  Observability is a passive subscriber,
not an event source.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from qzdap_schema.ids import (
    CostRecordId,
    RunRecordId,
    TenantId,
    WorkspaceId,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from qzdap.modules.observability_module.adapter.persistence.mappers import (
    cost_record_to_domain,
    cost_record_to_orm,
    run_record_to_domain,
    run_record_to_orm,
)
from qzdap.modules.observability_module.adapter.persistence.models import (
    CostRecordORM,
    RunRecordORM,
)
from qzdap.modules.observability_module.application.ports import (
    CostRecordRepository,
    RunRecordRepository,
)
from qzdap.modules.observability_module.domain.entities import (
    CostRecord,
    RunRecord,
)
from qzdap.modules.observability_module.domain.value_objects import (
    CostType,
    RunType,
)

# ── RunRecordRepository ───────────────────────────────────────────────────


class SqlRunRecordRepository(RunRecordRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, record: RunRecord) -> RunRecord:
        row = run_record_to_orm(record)
        self._session.add(row)
        await self._session.flush()
        return run_record_to_domain(row)

    async def get(
        self, *, tenant_id: TenantId, run_id: RunRecordId
    ) -> RunRecord | None:
        result = await self._session.execute(
            select(RunRecordORM).where(
                RunRecordORM.tenant_id == tenant_id,
                RunRecordORM.id == run_id,
            )
        )
        row = result.scalar_one_or_none()
        return run_record_to_domain(row) if row is not None else None

    async def list_records(
        self,
        *,
        tenant_id: TenantId,
        workspace_id: WorkspaceId | None,
        run_type: RunType | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[RunRecord]:
        if limit <= 0:
            raise ValueError("limit must be > 0")
        stmt = (
            select(RunRecordORM)
            .where(RunRecordORM.tenant_id == tenant_id)
            .order_by(RunRecordORM.completed_at.desc())
            .limit(limit)
            .offset(max(0, offset))
        )
        if workspace_id is not None:
            stmt = stmt.where(RunRecordORM.workspace_id == workspace_id)
        if run_type is not None:
            stmt = stmt.where(RunRecordORM.run_type == run_type.value)
        result = await self._session.execute(stmt)
        return [run_record_to_domain(r) for r in result.scalars().all()]


# ── CostRecordRepository ──────────────────────────────────────────────────


class SqlCostRecordRepository(CostRecordRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, record: CostRecord) -> CostRecord:
        row = cost_record_to_orm(record)
        self._session.add(row)
        await self._session.flush()
        return cost_record_to_domain(row)

    async def get(
        self, *, tenant_id: TenantId, cost_id: CostRecordId
    ) -> CostRecord | None:
        result = await self._session.execute(
            select(CostRecordORM).where(
                CostRecordORM.tenant_id == tenant_id,
                CostRecordORM.id == cost_id,
            )
        )
        row = result.scalar_one_or_none()
        return cost_record_to_domain(row) if row is not None else None

    async def list_records(
        self,
        *,
        tenant_id: TenantId,
        workspace_id: WorkspaceId | None,
        cost_type: CostType | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[CostRecord]:
        if limit <= 0:
            raise ValueError("limit must be > 0")
        stmt = (
            select(CostRecordORM)
            .where(CostRecordORM.tenant_id == tenant_id)
            .order_by(CostRecordORM.created_at.desc())
            .limit(limit)
            .offset(max(0, offset))
        )
        if workspace_id is not None:
            stmt = stmt.where(CostRecordORM.workspace_id == workspace_id)
        if cost_type is not None:
            stmt = stmt.where(CostRecordORM.cost_type == cost_type.value)
        if since is not None:
            stmt = stmt.where(CostRecordORM.created_at >= since)
        if until is not None:
            stmt = stmt.where(CostRecordORM.created_at <= until)
        result = await self._session.execute(stmt)
        return [cost_record_to_domain(r) for r in result.scalars().all()]

    # ── aggregations ─────────────────────────────────────────────────────

    async def sum_by_cost_type(
        self,
        *,
        tenant_id: TenantId,
        workspace_id: WorkspaceId | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> list[dict[str, Any]]:
        stmt = (
            select(CostRecordORM.cost_type, func.sum(CostRecordORM.amount_usd))
            .where(CostRecordORM.tenant_id == tenant_id)
            .group_by(CostRecordORM.cost_type)
        )
        if workspace_id is not None:
            stmt = stmt.where(CostRecordORM.workspace_id == workspace_id)
        if since is not None:
            stmt = stmt.where(CostRecordORM.created_at >= since)
        if until is not None:
            stmt = stmt.where(CostRecordORM.created_at <= until)
        result = await self._session.execute(stmt)
        return [
            {"cost_type": ct, "total_usd": _decimal_to_str(total)}
            for ct, total in result.all()
        ]

    async def sum_by_workspace(
        self,
        *,
        tenant_id: TenantId,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> list[dict[str, Any]]:
        stmt = (
            select(CostRecordORM.workspace_id, func.sum(CostRecordORM.amount_usd))
            .where(CostRecordORM.tenant_id == tenant_id)
            .group_by(CostRecordORM.workspace_id)
        )
        if since is not None:
            stmt = stmt.where(CostRecordORM.created_at >= since)
        if until is not None:
            stmt = stmt.where(CostRecordORM.created_at <= until)
        result = await self._session.execute(stmt)
        return [
            {"workspace_id": str(wid), "total_usd": _decimal_to_str(total)}
            for wid, total in result.all()
        ]

    async def sum_by_model(
        self,
        *,
        tenant_id: TenantId,
        workspace_id: WorkspaceId | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> list[dict[str, Any]]:
        stmt = (
            select(CostRecordORM.model_id, func.sum(CostRecordORM.amount_usd))
            .where(CostRecordORM.tenant_id == tenant_id)
            .group_by(CostRecordORM.model_id)
        )
        if workspace_id is not None:
            stmt = stmt.where(CostRecordORM.workspace_id == workspace_id)
        if since is not None:
            stmt = stmt.where(CostRecordORM.created_at >= since)
        if until is not None:
            stmt = stmt.where(CostRecordORM.created_at <= until)
        result = await self._session.execute(stmt)
        return [
            {"model_id": mid or "unknown", "total_usd": _decimal_to_str(total)}
            for mid, total in result.all()
        ]


def _decimal_to_str(value: Any) -> str:
    if value is None:
        return "0"
    return str(Decimal(str(value)))


__all__ = [
    "SqlCostRecordRepository",
    "SqlRunRecordRepository",
]
