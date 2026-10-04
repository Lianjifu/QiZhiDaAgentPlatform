"""HTTP adapter for admin workflows + user catalog.

Routes (mounted as-is so the web client does not need a rewrite):

  GET/POST     /api/admin/workflows
  GET/PATCH/DELETE /api/admin/workflows/{id}
  GET          /api/catalog/workflows
  GET          /api/catalog/workflows/__runs__
  POST         /api/catalog/workflows/{id}/favorite
  POST         /api/catalog/workflows/{id}/run
  aliases      /api/user/automations*
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request

from qzdap.modules.orchestration.application.services import OrchestrationService


def _owner_id(request: Request, fallback: UUID) -> UUID:
    principal = getattr(request.state, "principal", None)
    pid = getattr(principal, "id", None)
    if pid is None:
        return fallback
    return UUID(str(pid))


async def orchestration_dependency(request: Request) -> OrchestrationService:
    factory = getattr(request.app.state, "orchestration_service_factory", None)
    container = getattr(request.app.state, "container", None)
    if factory is None or container is None:
        raise HTTPException(status_code=503, detail="orchestration factory not wired")
    sf = container.session_factory()
    async with sf.session() as session:
        svc = factory.for_session(session)
        try:
            yield svc
        except Exception:
            await session.rollback()
            raise
        await session.commit()


def build_router() -> APIRouter:
    router = APIRouter(tags=["workflows"])

    @router.get("/api/admin/workflows")
    async def list_admin_workflows(
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        status: str = Query(default="all"),
        q: str = Query(default=""),
        svc: OrchestrationService = Depends(orchestration_dependency),  # noqa: B008
    ) -> list[dict[str, Any]]:
        return await svc.list_admin(workspace_id=x_workspace_id, status_filter=status, q=q)

    @router.post("/api/admin/workflows", status_code=201)
    async def create_admin_workflow(
        body: dict[str, Any],
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        svc: OrchestrationService = Depends(orchestration_dependency),  # noqa: B008
    ) -> dict[str, Any]:
        return await svc.create(
            tenant_id=x_tenant_id, workspace_id=x_workspace_id, body=body
        )

    @router.get("/api/admin/workflows/{workflow_id}")
    async def get_admin_workflow(
        workflow_id: UUID,
        svc: OrchestrationService = Depends(orchestration_dependency),  # noqa: B008
    ) -> dict[str, Any]:
        return await svc.get_admin(workflow_id)

    @router.patch("/api/admin/workflows/{workflow_id}")
    async def patch_admin_workflow(
        workflow_id: UUID,
        body: dict[str, Any],
        request: Request,
        x_user_id: UUID = Header(default=UUID(int=0), alias="X-User-Id"),  # noqa: B008
        svc: OrchestrationService = Depends(orchestration_dependency),  # noqa: B008
    ) -> dict[str, Any]:
        actor = str(_owner_id(request, x_user_id))
        return await svc.update(workflow_id=workflow_id, body=body, actor=actor)

    @router.delete("/api/admin/workflows/{workflow_id}")
    async def delete_admin_workflow(
        workflow_id: UUID,
        svc: OrchestrationService = Depends(orchestration_dependency),  # noqa: B008
    ) -> dict[str, Any]:
        return await svc.delete(workflow_id)

    @router.get("/api/catalog/workflows")
    async def list_catalog_workflows(
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        svc: OrchestrationService = Depends(orchestration_dependency),  # noqa: B008
    ) -> list[dict[str, Any]]:
        return await svc.list_catalog(workspace_id=x_workspace_id)

    @router.get("/api/catalog/workflows/__runs__")
    async def list_catalog_runs(
        request: Request,
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        x_user_id: UUID = Header(default=UUID(int=0), alias="X-User-Id"),  # noqa: B008
        svc: OrchestrationService = Depends(orchestration_dependency),  # noqa: B008
    ) -> list[dict[str, Any]]:
        user_id = _owner_id(request, x_user_id)
        return await svc.list_runs(workspace_id=x_workspace_id, user_id=user_id)

    @router.post("/api/catalog/workflows/{workflow_id}/favorite")
    async def favorite_catalog_workflow(
        workflow_id: UUID,
        body: dict[str, Any],
        request: Request,
        x_user_id: UUID = Header(default=UUID(int=0), alias="X-User-Id"),  # noqa: B008
        svc: OrchestrationService = Depends(orchestration_dependency),  # noqa: B008
    ) -> dict[str, Any]:
        user_id = _owner_id(request, x_user_id)
        return await svc.set_favorite(
            workflow_id=workflow_id, user_id=user_id, on=bool(body.get("on"))
        )

    @router.post("/api/catalog/workflows/{workflow_id}/run")
    async def run_catalog_workflow(
        workflow_id: UUID,
        body: dict[str, Any],
        request: Request,
        x_user_id: UUID = Header(default=UUID(int=0), alias="X-User-Id"),  # noqa: B008
        svc: OrchestrationService = Depends(orchestration_dependency),  # noqa: B008
    ) -> dict[str, Any]:
        user_id = _owner_id(request, x_user_id)
        note = body.get("note") if isinstance(body, dict) else None
        return await svc.record_run(
            workflow_id=workflow_id,
            user_id=user_id,
            note=str(note) if note is not None else None,
        )

    @router.get("/api/user/automations")
    async def list_user_automations_alias(
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        svc: OrchestrationService = Depends(orchestration_dependency),  # noqa: B008
    ) -> list[dict[str, Any]]:
        return await svc.list_catalog(workspace_id=x_workspace_id)

    @router.get("/api/user/automations/__runs__")
    async def list_user_automation_runs_alias(
        request: Request,
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        x_user_id: UUID = Header(default=UUID(int=0), alias="X-User-Id"),  # noqa: B008
        svc: OrchestrationService = Depends(orchestration_dependency),  # noqa: B008
    ) -> list[dict[str, Any]]:
        user_id = _owner_id(request, x_user_id)
        return await svc.list_runs(workspace_id=x_workspace_id, user_id=user_id)

    @router.post("/api/user/automations/{workflow_id}/favorite")
    async def favorite_user_automation_alias(
        workflow_id: UUID,
        body: dict[str, Any],
        request: Request,
        x_user_id: UUID = Header(default=UUID(int=0), alias="X-User-Id"),  # noqa: B008
        svc: OrchestrationService = Depends(orchestration_dependency),  # noqa: B008
    ) -> dict[str, Any]:
        user_id = _owner_id(request, x_user_id)
        return await svc.set_favorite(
            workflow_id=workflow_id, user_id=user_id, on=bool(body.get("on"))
        )

    @router.post("/api/user/automations/{workflow_id}/run")
    async def run_user_automation_alias(
        workflow_id: UUID,
        body: dict[str, Any],
        request: Request,
        x_user_id: UUID = Header(default=UUID(int=0), alias="X-User-Id"),  # noqa: B008
        svc: OrchestrationService = Depends(orchestration_dependency),  # noqa: B008
    ) -> dict[str, Any]:
        user_id = _owner_id(request, x_user_id)
        note = body.get("note") if isinstance(body, dict) else None
        return await svc.record_run(
            workflow_id=workflow_id,
            user_id=user_id,
            note=str(note) if note is not None else None,
        )

    return router
