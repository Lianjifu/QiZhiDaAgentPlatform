"""Application ports (Protocols) for the observability module.

These define the inbound / outbound seams between the domain and
adapters.  All ports are ``@runtime_checkable`` Protocols so adapters
can satisfy them structurally (mypy-validated at the boundary).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from qzdap_schema.ids import (
    AgentTemplateId,
    AgentVersionId,
    CostRecordId,
    RunRecordId,
    TenantId,
    WorkspaceId,
)

from qzdap.modules.observability_module.domain.entities import (
    CostRecord,
    RunRecord,
)
from qzdap.modules.observability_module.domain.value_objects import (
    CostType,
    RunType,
)

# ── Repositories ─────────────────────────────────────────────────────────


@runtime_checkable
class RunRecordRepository(Protocol):
    async def add(self, record: RunRecord) -> RunRecord: ...
    async def get(
        self, *, tenant_id: TenantId, run_id: RunRecordId
    ) -> RunRecord | None: ...
    async def list_records(
        self,
        *,
        tenant_id: TenantId,
        workspace_id: WorkspaceId | None,
        run_type: RunType | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[RunRecord]: ...


@runtime_checkable
class CostRecordRepository(Protocol):
    async def add(self, record: CostRecord) -> CostRecord: ...
    async def get(
        self, *, tenant_id: TenantId, cost_id: CostRecordId
    ) -> CostRecord | None: ...
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
    ) -> list[CostRecord]: ...
    async def sum_by_cost_type(
        self,
        *,
        tenant_id: TenantId,
        workspace_id: WorkspaceId | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> list[dict[str, Any]]: ...

    async def sum_by_workspace(
        self,
        *,
        tenant_id: TenantId,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> list[dict[str, Any]]: ...

    async def sum_by_model(
        self,
        *,
        tenant_id: TenantId,
        workspace_id: WorkspaceId | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> list[dict[str, Any]]: ...


# ── Event publisher (internal — emitted when we record an event) ────────


@runtime_checkable
class ObservabilityEventPublisher(Protocol):
    async def publish(self, event: object) -> None: ...


# ── Cross-module query port (live aggregate from eval_runs) ──────────────


@runtime_checkable
class EvalRunQueryPort(Protocol):
    """Used by the QualityScore read-through use case.

    Returns the latest passed EvalRun for ``(template_id, version_id)``
    or ``None``.  Implemented by ``EvaluationServiceAdapter`` from
    ``modules/evaluation``.
    """

    async def latest_passed_run(
        self,
        *,
        tenant_id: TenantId,
        template_id: AgentTemplateId,
        version_id: AgentVersionId,
    ) -> object | None: ...


__all__ = [
    "CostRecordRepository",
    "EvalRunQueryPort",
    "ObservabilityEventPublisher",
    "RunRecordRepository",
]
