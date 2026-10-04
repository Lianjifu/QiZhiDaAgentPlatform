"""HTTP router for the observability module.

Mounts under ``/v1/observability``.  Per-request service is resolved
via :func:`observability_service_dependency`.

Endpoints (v1):

- GET  /v1/observability/runs                              → list RunRecords
- GET  /v1/observability/costs                             → list CostRecords
- GET  /v1/observability/costs?group_by=cost_type|model
                                                  → aggregate (group_by options)
- GET  /v1/observability/quality/{template_id}/{version_id}
                                                            → QualityScore
                                                            read-through
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request

from qzdap.modules.observability_module.adapter.http.dto import (
    CostAggregateItem,
    CostAggregateResponse,
    CostRecordListResponse,
    QualityScoreResponse,
    RunRecordListResponse,
)
from qzdap.modules.observability_module.adapter.http.factory import (
    ObservabilityServiceFactory,
)
from qzdap.modules.observability_module.adapter.http.mappers import (
    cost_record_to_dto,
    quality_score_to_dto,
    run_record_to_dto,
)
from qzdap.modules.observability_module.application.services import (
    ObservabilityService,
)
from qzdap.modules.observability_module.domain.errors import (
    QualityScoreNotFound,
)


async def observability_service_dependency(
    request: Request,
) -> ObservabilityService:
    factory: ObservabilityServiceFactory | None = getattr(
        request.app.state, "observability_service_factory", None
    )
    if factory is None:
        raise HTTPException(
            status_code=503,
            detail="observability service factory not wired",
        )
    return factory.for_session()


def build_router() -> APIRouter:
    router = APIRouter(prefix="/v1/observability", tags=["observability"])

    @router.get(
        "/runs",
        response_model=RunRecordListResponse,
    )
    async def list_runs(
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        svc: ObservabilityService = Depends(observability_service_dependency),  # noqa: B008
        run_type: str | None = Query(None),
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
    ) -> RunRecordListResponse:
        from qzdap_schema.ids import TenantId, WorkspaceId

        from qzdap.modules.observability_module.domain.value_objects import RunType

        rt_enum: RunType | None = None
        if run_type is not None:
            try:
                rt_enum = RunType(run_type)
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc))

        rows = await svc.list_runs(
            tenant_id=TenantId(x_tenant_id),
            workspace_id=WorkspaceId(x_workspace_id),
            run_type=rt_enum,
            limit=limit,
            offset=offset,
        )
        return RunRecordListResponse(
            items=[run_record_to_dto(r) for r in rows],
            count=len(rows),
        )

    @router.get(
        "/costs",
        response_model=CostRecordListResponse | CostAggregateResponse,
    )
    async def list_or_aggregate_costs(
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        svc: ObservabilityService = Depends(observability_service_dependency),  # noqa: B008
        cost_type: str | None = Query(None),
        group_by: Literal["cost_type", "workspace", "model"] | None = Query(None),
        since: datetime | None = Query(None),  # noqa: B008 — FastAPI idiom
        until: datetime | None = Query(None),  # noqa: B008 — FastAPI idiom
        limit: int = Query(200, ge=1, le=500),
        offset: int = Query(0, ge=0),
    ):
        from qzdap_schema.ids import TenantId, WorkspaceId

        from qzdap.modules.observability_module.domain.value_objects import CostType

        ct_enum: CostType | None = None
        if cost_type is not None:
            try:
                ct_enum = CostType(cost_type)
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc))

        if group_by is not None:
            rows = await svc.aggregate_costs(
                tenant_id=TenantId(x_tenant_id),
                workspace_id=WorkspaceId(x_workspace_id),
                group_by=group_by,
                since=since,
                until=until,
            )
            return CostAggregateResponse(
                group_by=group_by,
                items=[
                    CostAggregateItem(
                        cost_type=row.get("cost_type"),
                        workspace_id=row.get("workspace_id"),
                        model_id=row.get("model_id"),
                        total_usd=row.get("total_usd", "0"),
                    )
                    for row in rows
                ],
                count=len(rows),
            )

        rows = await svc.list_costs(
            tenant_id=TenantId(x_tenant_id),
            workspace_id=WorkspaceId(x_workspace_id),
            cost_type=ct_enum,
            since=since,
            until=until,
            limit=limit,
            offset=offset,
        )
        return CostRecordListResponse(
            items=[cost_record_to_dto(r) for r in rows],
            count=len(rows),
        )

    @router.get(
        "/quality/{template_id}/{version_id}",
        response_model=QualityScoreResponse,
    )
    async def get_quality_score(
        template_id: UUID,
        version_id: UUID,
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        svc: ObservabilityService = Depends(observability_service_dependency),  # noqa: B008
    ) -> QualityScoreResponse:
        from qzdap_schema.ids import (
            AgentTemplateId,
            AgentVersionId,
            TenantId,
        )

        score = await svc.get_quality_score(
            tenant_id=TenantId(x_tenant_id),
            template_id=AgentTemplateId(template_id),
            version_id=AgentVersionId(version_id),
        )
        if score is None:
            raise HTTPException(
                status_code=404,
                detail=QualityScoreNotFound(
                    "no passed eval run for (template_id, version_id)"
                ).code,
            )
        return quality_score_to_dto(score)

    return router


__all__ = ["build_router", "observability_service_dependency"]
