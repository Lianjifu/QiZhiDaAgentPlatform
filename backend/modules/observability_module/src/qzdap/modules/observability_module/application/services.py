"""ObservabilityService — wires ports into the use cases.

``from_parts`` is the canonical factory: it accepts run + cost
repositories, a pricing catalog, the eval cross-module port, and
constructs the use case closures.  HTTP dependencies call
``from_parts`` (or use the factory closure built in lifespan) and
expose ``.list_runs()`` / ``.list_costs()`` / ``.aggregate_costs()`` /
``.get_quality_score()`` etc.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from qzdap_schema.ids import (
    AgentTemplateId,
    AgentVersionId,
    TenantId,
    WorkspaceId,
)

from qzdap.modules.observability_module.application.ports import (
    CostRecordRepository,
    EvalRunQueryPort,
    ObservabilityEventPublisher,
    RunRecordRepository,
)
from qzdap.modules.observability_module.application.pricing import PricingCatalog
from qzdap.modules.observability_module.domain.value_objects import (
    CostType,
    RunType,
)

# Aggregator row shape: list[dict[str, Any]] returned from repo.sum_*.
AggregateRow = dict[str, Any]


# Use-case command types (plain dicts — keep DTO-free inside the
# application boundary; HTTP layer wraps with Pydantic).
RecordRunCmd = dict[str, Any]
RecordCostCmd = dict[str, Any]


# ── Service ─────────────────────────────────────────────────────────────────────────────────────────────────


@dataclass(slots=True)
class ObservabilityService:
    """Container of use cases wired from ports."""

    run_repo: RunRecordRepository
    cost_repo: CostRecordRepository
    pricing: PricingCatalog
    eval_query: EvalRunQueryPort | None = None
    publisher: ObservabilityEventPublisher | None = None

    # Cache the use-case callables (closures) so HTTP handlers can call
    # ``svc.list_runs(...)`` without re-importing.
    _use_cases: dict[str, Callable[..., Awaitable[Any]]] = field(
        default_factory=dict, repr=False
    )

    def __post_init__(self) -> None:
        from qzdap.modules.observability_module.application.use_cases import (
            aggregate_costs,
            get_quality_score,
            list_costs,
            list_runs,
            record_cost,
            record_run,
        )

        self._use_cases = {
            "record_run": record_run.build(self),
            "record_cost": record_cost.build(self),
            "list_runs": list_runs.build(self),
            "list_costs": list_costs.build(self),
            "aggregate_costs": aggregate_costs.build(self),
            "get_quality_score": get_quality_score.build(self),
        }

    # ── method proxies ──────────────────────────────────────────────────

    async def record_run(self, *, cmd: RecordRunCmd) -> Any:
        return await self._use_cases["record_run"](cmd)

    async def record_cost(self, *, cmd: RecordCostCmd) -> Any:
        return await self._use_cases["record_cost"](cmd)

    async def list_runs(
        self,
        *,
        tenant_id: TenantId,
        workspace_id: WorkspaceId | None,
        run_type: RunType | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Any]:
        return await self._use_cases["list_runs"](
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            run_type=run_type,
            limit=limit,
            offset=offset,
        )

    async def list_costs(
        self,
        *,
        tenant_id: TenantId,
        workspace_id: WorkspaceId | None,
        cost_type: CostType | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[Any]:
        return await self._use_cases["list_costs"](
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            cost_type=cost_type,
            since=since,
            until=until,
            limit=limit,
            offset=offset,
        )

    async def aggregate_costs(
        self,
        *,
        tenant_id: TenantId,
        workspace_id: WorkspaceId | None = None,
        group_by: str = "cost_type",
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> list[AggregateRow]:
        return await self._use_cases["aggregate_costs"](
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            group_by=group_by,
            since=since,
            until=until,
        )

    async def get_quality_score(
        self,
        *,
        tenant_id: TenantId,
        template_id: AgentTemplateId,
        version_id: AgentVersionId,
    ) -> Any:
        return await self._use_cases["get_quality_score"](
            tenant_id=tenant_id,
            template_id=template_id,
            version_id=version_id,
        )

    # ── factory ─────────────────────────────────────────────────────────

    @classmethod
    def from_parts(
        cls,
        *,
        run_repo: RunRecordRepository,
        cost_repo: CostRecordRepository,
        pricing: PricingCatalog,
        eval_query: EvalRunQueryPort | None = None,
        publisher: ObservabilityEventPublisher | None = None,
    ) -> ObservabilityService:
        return cls(
            run_repo=run_repo,
            cost_repo=cost_repo,
            pricing=pricing,
            eval_query=eval_query,
            publisher=publisher,
        )


__all__ = ["ObservabilityService"]
