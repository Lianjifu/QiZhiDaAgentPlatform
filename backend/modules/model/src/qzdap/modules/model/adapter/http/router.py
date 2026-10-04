"""HTTP adapter for admin model catalog.

  GET          /api/admin/models
  GET          /api/admin/models/providers
  GET          /api/admin/models/routes
  GET          /api/admin/models/health
  POST         /api/admin/models/catalog
  POST         /api/admin/models
  POST         /api/admin/models/routes
  POST         /api/admin/models/batch-status
  GET/PATCH/DELETE /api/admin/models/{id}
  POST         /api/admin/models/{id}/star
  POST         /api/admin/models/routes/{id}/toggle
  DELETE       /api/admin/models/routes/{id}
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request

from qzdap.modules.model.application.services import ModelService


async def model_dependency(request: Request) -> ModelService:
    factory = getattr(request.app.state, "model_service_factory", None)
    container = getattr(request.app.state, "container", None)
    if factory is None or container is None:
        raise HTTPException(status_code=503, detail="model factory not wired")
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
    router = APIRouter(tags=["models"])

    @router.get("/api/admin/models")
    async def list_admin_models(
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        search: str = Query(default=""),
        status: str = Query(default="all"),
        tier: str = Query(default="all"),
        svc: ModelService = Depends(model_dependency),  # noqa: B008
    ) -> list[dict[str, Any]]:
        return await svc.list_models(
            workspace_id=x_workspace_id, search=search, status=status, tier=tier
        )

    @router.get("/api/admin/models/providers")
    async def list_admin_providers(
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        svc: ModelService = Depends(model_dependency),  # noqa: B008
    ) -> list[dict[str, Any]]:
        return await svc.list_providers(workspace_id=x_workspace_id)

    @router.get("/api/admin/models/routes")
    async def list_admin_routes(
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        svc: ModelService = Depends(model_dependency),  # noqa: B008
    ) -> list[dict[str, Any]]:
        return await svc.list_routes(workspace_id=x_workspace_id)

    @router.get("/api/admin/models/health")
    async def list_admin_health(
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        svc: ModelService = Depends(model_dependency),  # noqa: B008
    ) -> list[dict[str, Any]]:
        return await svc.list_health(workspace_id=x_workspace_id)

    @router.post("/api/admin/models/catalog")
    async def probe_catalog(
        body: dict[str, Any],
        svc: ModelService = Depends(model_dependency),  # noqa: B008
    ) -> dict[str, Any]:
        return await svc.probe_catalog(body)

    @router.post("/api/admin/models", status_code=201)
    async def create_admin_models(
        body: dict[str, Any],
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        svc: ModelService = Depends(model_dependency),  # noqa: B008
    ) -> dict[str, Any]:
        try:
            return await svc.create_from_provider(
                tenant_id=x_tenant_id, workspace_id=x_workspace_id, body=body
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.post("/api/admin/models/routes", status_code=201)
    async def create_admin_route(
        body: dict[str, Any],
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        svc: ModelService = Depends(model_dependency),  # noqa: B008
    ) -> dict[str, Any]:
        return await svc.create_route(
            tenant_id=x_tenant_id, workspace_id=x_workspace_id, body=body
        )

    @router.post("/api/admin/models/batch-status")
    async def batch_admin_status(
        body: dict[str, Any],
        svc: ModelService = Depends(model_dependency),  # noqa: B008
    ) -> dict[str, Any]:
        return await svc.batch_status(
            ids=[str(item) for item in (body.get("ids") or [])],
            status=str(body.get("status") or "draft"),
        )

    @router.get("/api/admin/models/{model_id}")
    async def get_admin_model(
        model_id: UUID,
        svc: ModelService = Depends(model_dependency),  # noqa: B008
    ) -> dict[str, Any]:
        return await svc.get_model(model_id)

    @router.patch("/api/admin/models/{model_id}")
    async def patch_admin_model(
        model_id: UUID,
        body: dict[str, Any],
        svc: ModelService = Depends(model_dependency),  # noqa: B008
    ) -> dict[str, Any]:
        return await svc.update_model(model_id=model_id, body=body)

    @router.delete("/api/admin/models/{model_id}")
    async def delete_admin_model(
        model_id: UUID,
        svc: ModelService = Depends(model_dependency),  # noqa: B008
    ) -> dict[str, Any]:
        return await svc.delete_model(model_id)

    @router.post("/api/admin/models/{model_id}/star")
    async def star_admin_model(
        model_id: UUID,
        body: dict[str, Any],
        svc: ModelService = Depends(model_dependency),  # noqa: B008
    ) -> dict[str, Any]:
        return await svc.set_starred(model_id=model_id, starred=bool(body.get("starred")))

    @router.post("/api/admin/models/routes/{route_id}/toggle")
    async def toggle_admin_route(
        route_id: UUID,
        svc: ModelService = Depends(model_dependency),  # noqa: B008
    ) -> dict[str, Any]:
        return await svc.toggle_route(route_id)

    @router.delete("/api/admin/models/routes/{route_id}")
    async def delete_admin_route(
        route_id: UUID,
        svc: ModelService = Depends(model_dependency),  # noqa: B008
    ) -> dict[str, Any]:
        return await svc.delete_route(route_id)

    return router
