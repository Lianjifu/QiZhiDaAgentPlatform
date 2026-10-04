"""In-memory test doubles for the observability module ports.

Implementations match the @runtime_checkable Protocols in
``application/ports.py``.  Stores are simple dicts; aggregations are
implemented as pure-Python reductions over the in-memory list.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from typing import Any

from qzdap_schema.ids import (
    AgentTemplateId,
    AgentVersionId,
    CostRecordId,
    RunRecordId,
    TenantId,
    WorkspaceId,
)

from qzdap.modules.observability_module.application.ports import (
    CostRecordRepository,
    EvalRunQueryPort,
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


class InMemoryRunRecordRepository(RunRecordRepository):
    def __init__(self) -> None:
        self._store: dict[RunRecordId, RunRecord] = {}

    async def add(self, record: RunRecord) -> RunRecord:
        self._store[record.id] = record
        return record

    async def get(
        self, *, tenant_id: TenantId, run_id: RunRecordId
    ) -> RunRecord | None:
        rec = self._store.get(run_id)
        if rec is not None and rec.tenant_id == tenant_id:
            return rec
        return None

    async def list_records(
        self,
        *,
        tenant_id: TenantId,
        workspace_id: WorkspaceId | None,
        run_type: RunType | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[RunRecord]:
        out: list[RunRecord] = []
        for rec in sorted(
            self._store.values(), key=lambda r: r.completed_at, reverse=True
        ):
            if rec.tenant_id != tenant_id:
                continue
            if workspace_id is not None and rec.workspace_id != workspace_id:
                continue
            if run_type is not None and rec.run_type != run_type:
                continue
            out.append(rec)
        return out[offset : offset + limit]


# ── CostRecordRepository ──────────────────────────────────────────────────


class InMemoryCostRecordRepository(CostRecordRepository):
    def __init__(self) -> None:
        self._store: dict[CostRecordId, CostRecord] = {}

    async def add(self, record: CostRecord) -> CostRecord:
        self._store[record.id] = record
        return record

    async def get(
        self, *, tenant_id: TenantId, cost_id: CostRecordId
    ) -> CostRecord | None:
        rec = self._store.get(cost_id)
        if rec is not None and rec.tenant_id == tenant_id:
            return rec
        return None

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
        out: list[CostRecord] = []
        for rec in sorted(
            self._store.values(), key=lambda r: r.created_at, reverse=True
        ):
            if rec.tenant_id != tenant_id:
                continue
            if workspace_id is not None and rec.workspace_id != workspace_id:
                continue
            if cost_type is not None and rec.cost_type != cost_type:
                continue
            if since is not None and rec.created_at < since:
                continue
            if until is not None and rec.created_at > until:
                continue
            out.append(rec)
        return out[offset : offset + limit]

    async def sum_by_cost_type(
        self,
        *,
        tenant_id: TenantId,
        workspace_id: WorkspaceId | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> list[dict[str, Any]]:
        buckets: dict[str, Decimal] = defaultdict(lambda: Decimal(0))
        for rec in self._store.values():
            if not _match(rec, tenant_id, workspace_id, since, until):
                continue
            buckets[rec.cost_type.value] += rec.amount_usd
        return [{"cost_type": k, "total_usd": _to_str(v)} for k, v in buckets.items()]

    async def sum_by_workspace(
        self,
        *,
        tenant_id: TenantId,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> list[dict[str, Any]]:
        buckets: dict[str, Decimal] = defaultdict(lambda: Decimal(0))
        for rec in self._store.values():
            if rec.tenant_id != tenant_id:
                continue
            if since is not None and rec.created_at < since:
                continue
            if until is not None and rec.created_at > until:
                continue
            buckets[str(rec.workspace_id)] += rec.amount_usd
        return [
            {"workspace_id": k, "total_usd": _to_str(v)} for k, v in buckets.items()
        ]

    async def sum_by_model(
        self,
        *,
        tenant_id: TenantId,
        workspace_id: WorkspaceId | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> list[dict[str, Any]]:
        buckets: dict[str, Decimal] = defaultdict(lambda: Decimal(0))
        for rec in self._store.values():
            if not _match(rec, tenant_id, workspace_id, since, until):
                continue
            key = rec.model_id or "unknown"
            buckets[key] += rec.amount_usd
        return [{"model_id": k, "total_usd": _to_str(v)} for k, v in buckets.items()]


def _match(
    rec: CostRecord,
    tenant_id: TenantId,
    workspace_id: WorkspaceId | None,
    since: datetime | None,
    until: datetime | None,
) -> bool:
    if rec.tenant_id != tenant_id:
        return False
    if workspace_id is not None and rec.workspace_id != workspace_id:
        return False
    if since is not None and rec.created_at < since:
        return False
    return not (until is not None and rec.created_at > until)


def _to_str(value: Decimal) -> str:
    return format(value, "f")


# ── EvalRunQueryPort ──────────────────────────────────────────────────────


class FakeEvalRunQueryPort(EvalRunQueryPort):
    """Returns a fixed ``FakeEvalRun`` from a tenant-keyed dict."""

    def __init__(self, runs: dict[tuple, dict[str, Any]] | None = None) -> None:
        self._runs = runs or {}

    async def latest_passed_run(
        self,
        *,
        tenant_id: TenantId,
        template_id: AgentTemplateId,
        version_id: AgentVersionId,
    ) -> object | None:
        return self._runs.get((str(tenant_id), str(template_id), str(version_id)))


__all__ = [
    "FakeEvalRunQueryPort",
    "InMemoryCostRecordRepository",
    "InMemoryRunRecordRepository",
]
