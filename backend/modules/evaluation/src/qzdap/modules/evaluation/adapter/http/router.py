"""HTTP router for the evaluation module: datasets, cases, runs.

Mounts under ``/v1/eval``.  Per-request service is resolved via
:func:`evaluation_service_dependency`.

Endpoints (v1):

- GET    /v1/eval/datasets                 → list datasets (workspace)
- GET    /v1/eval/datasets/{did}           → get dataset
- GET    /v1/eval/datasets/{did}/cases     → list cases for a dataset
- GET    /v1/eval/runs                     → list runs (filterable)
- POST   /v1/eval/runs                     → start run (returns 202)
- GET    /v1/eval/runs/{rid}               → get run
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request

from qzdap.modules.evaluation.adapter.http.dto import (
    CaseListResponse,
    DatasetListResponse,
    DatasetResponse,
    RunListResponse,
    RunResponse,
    StartRunRequest,
)
from qzdap.modules.evaluation.adapter.http.mappers import (
    case_to_dto,
    dataset_to_dto,
    run_to_dto,
)
from qzdap.modules.evaluation.application.services import EvaluationService
from qzdap.modules.evaluation.domain.errors import (
    EvalDatasetNotFound,
    EvalRunNotFound,
    EvaluationError,
    IdempotencyKeyConflict,
)


async def evaluation_service_dependency(
    request: Request,
) -> EvaluationService:
    """Yield a per-request ``EvaluationService``.

    Production wires ``EvaluationServiceFactory`` via ``app.state``;
    when the factory is missing we surface 503.
    """
    factory = getattr(request.app.state, "evaluation_service_factory", None)
    if factory is None:
        raise HTTPException(
            status_code=503,
            detail="evaluation service factory not wired",
        )
    return factory.for_session()


def _domain_error_to_http(exc: Exception) -> HTTPException:
    if isinstance(exc, (EvalDatasetNotFound, EvalRunNotFound)):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, IdempotencyKeyConflict):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, EvaluationError):
        return HTTPException(status_code=400, detail=str(exc))
    return HTTPException(status_code=500, detail=str(exc))


def build_router() -> APIRouter:
    router = APIRouter(prefix="/v1/eval", tags=["evaluation"])

    # ── datasets ───────────────────────────────────────────────────────

    @router.get(
        "/datasets",
        response_model=DatasetListResponse,
    )
    async def list_datasets(
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        svc: EvaluationService = Depends(evaluation_service_dependency),  # noqa: B008
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
    ) -> DatasetListResponse:
        from qzdap_schema.ids import TenantId, WorkspaceId

        rows = await svc.list_datasets.execute(  # type: ignore[union-attr]
            tenant_id=TenantId(x_tenant_id),
            workspace_id=WorkspaceId(x_workspace_id),
            limit=limit,
            offset=offset,
        )
        return DatasetListResponse(
            items=[dataset_to_dto(r) for r in rows],
            count=len(rows),
        )

    @router.get(
        "/datasets/{did}",
        response_model=DatasetResponse,
    )
    async def get_dataset(
        did: UUID,
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        svc: EvaluationService = Depends(evaluation_service_dependency),  # noqa: B008
    ) -> DatasetResponse:
        from qzdap_schema.ids import EvalDatasetId, TenantId

        try:
            dataset = await svc.get_dataset.execute(  # type: ignore[union-attr]
                tenant_id=TenantId(x_tenant_id),
                dataset_id=EvalDatasetId(did),
            )
        except Exception as exc:  # noqa: BLE001
            raise _domain_error_to_http(exc)
        return dataset_to_dto(dataset)

    @router.get(
        "/datasets/{did}/cases",
        response_model=CaseListResponse,
    )
    async def list_cases(
        did: UUID,
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        svc: EvaluationService = Depends(evaluation_service_dependency),  # noqa: B008
    ) -> CaseListResponse:
        from qzdap_schema.ids import EvalDatasetId, TenantId

        rows = await svc.list_cases.execute(  # type: ignore[union-attr]
            tenant_id=TenantId(x_tenant_id),
            dataset_id=EvalDatasetId(did),
        )
        return CaseListResponse(
            items=[case_to_dto(r) for r in rows],
            count=len(rows),
        )

    # ── runs ────────────────────────────────────────────────────────────

    @router.post(
        "/runs",
        status_code=202,
        response_model=RunResponse,
    )
    async def start_run(
        body: StartRunRequest,
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        x_user_id: UUID = Header(..., alias="X-User-Id"),  # noqa: B008
        svc: EvaluationService = Depends(evaluation_service_dependency),  # noqa: B008
    ) -> RunResponse:
        from qzdap_schema.ids import (
            AgentTemplateId,
            AgentVersionId,
            EvalDatasetId,
            TenantId,
            UserId,
            WorkspaceId,
        )

        try:
            run = await svc.start_run.execute(  # type: ignore[union-attr]
                tenant_id=TenantId(x_tenant_id),
                workspace_id=WorkspaceId(x_workspace_id),
                dataset_id=EvalDatasetId(body.dataset_id),
                template_id=AgentTemplateId(body.template_id),
                version_id=AgentVersionId(body.version_id),
                triggered_by=UserId(x_user_id),
                idempotency_key=body.idempotency_key,
            )
        except Exception as exc:  # noqa: BLE001
            raise _domain_error_to_http(exc)
        return run_to_dto(run)

    @router.get(
        "/runs",
        response_model=RunListResponse,
    )
    async def list_runs(
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        svc: EvaluationService = Depends(evaluation_service_dependency),  # noqa: B008
        template_id: UUID | None = Query(default=None),  # noqa: B008
        version_id: UUID | None = Query(default=None),  # noqa: B008
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
    ) -> RunListResponse:
        from qzdap_schema.ids import (
            AgentTemplateId,
            AgentVersionId,
            TenantId,
            WorkspaceId,
        )

        rows = await svc.list_runs.execute(  # type: ignore[union-attr]
            tenant_id=TenantId(x_tenant_id),
            workspace_id=WorkspaceId(x_workspace_id),
            template_id=AgentTemplateId(template_id) if template_id else None,
            version_id=AgentVersionId(version_id) if version_id else None,
            limit=limit,
            offset=offset,
        )
        return RunListResponse(
            items=[run_to_dto(r) for r in rows],
            count=len(rows),
        )

    @router.get(
        "/runs/{rid}",
        response_model=RunResponse,
    )
    async def get_run(
        rid: UUID,
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        svc: EvaluationService = Depends(evaluation_service_dependency),  # noqa: B008
    ) -> RunResponse:
        from qzdap_schema.ids import EvalRunId, TenantId

        try:
            run = await svc.get_run.execute(  # type: ignore[union-attr]
                tenant_id=TenantId(x_tenant_id),
                run_id=EvalRunId(rid),
            )
        except Exception as exc:  # noqa: BLE001
            raise _domain_error_to_http(exc)
        return run_to_dto(run)

    return router


__all__ = ["build_router", "evaluation_service_dependency"]
