"""HTTP adapter for admin memory catalog.

  GET /api/admin/memory/l1
  GET /api/admin/memory/l1/{id}
  GET /api/admin/memory/l2
  GET /api/admin/memory/l2/{id}
  GET /api/admin/memory/l3
  GET /api/admin/memory/l3/{id}
  GET /api/admin/memory/promotions
  GET /api/admin/memory/policies
  GET /api/admin/memory/policies/{label}
  GET /api/admin/memory/trend
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request

from qzdap.modules.memory.application.services import MemoryService


async def memory_dependency(request: Request) -> MemoryService:
    factory = getattr(request.app.state, "memory_service_factory", None)
    container = getattr(request.app.state, "container", None)
    if factory is None or container is None:
        raise HTTPException(status_code=503, detail="memory factory not wired")
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
    router = APIRouter(tags=["memory"])

    @router.get("/api/admin/memory/l1")
    async def list_l1(
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        svc: MemoryService = Depends(memory_dependency),  # noqa: B008
    ) -> list[dict[str, Any]]:
        return await svc.list_l1(workspace_id=x_workspace_id)

    @router.get("/api/admin/memory/l1/{item_id}")
    async def get_l1(
        item_id: UUID,
        svc: MemoryService = Depends(memory_dependency),  # noqa: B008
    ) -> dict[str, Any]:
        return await svc.get_l1(item_id)

    @router.get("/api/admin/memory/l2")
    async def list_l2(
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        svc: MemoryService = Depends(memory_dependency),  # noqa: B008
    ) -> list[dict[str, Any]]:
        return await svc.list_l2(workspace_id=x_workspace_id)

    @router.get("/api/admin/memory/l2/{item_id}")
    async def get_l2(
        item_id: UUID,
        svc: MemoryService = Depends(memory_dependency),  # noqa: B008
    ) -> dict[str, Any]:
        return await svc.get_l2(item_id)

    @router.get("/api/admin/memory/l3")
    async def list_l3(
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        svc: MemoryService = Depends(memory_dependency),  # noqa: B008
    ) -> list[dict[str, Any]]:
        return await svc.list_l3(workspace_id=x_workspace_id)

    @router.get("/api/admin/memory/l3/{item_id}")
    async def get_l3(
        item_id: UUID,
        svc: MemoryService = Depends(memory_dependency),  # noqa: B008
    ) -> dict[str, Any]:
        return await svc.get_l3(item_id)

    @router.get("/api/admin/memory/promotions")
    async def list_promotions(
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        svc: MemoryService = Depends(memory_dependency),  # noqa: B008
    ) -> list[dict[str, Any]]:
        return await svc.list_promotions(workspace_id=x_workspace_id)

    @router.get("/api/admin/memory/policies")
    async def list_policies(
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        svc: MemoryService = Depends(memory_dependency),  # noqa: B008
    ) -> list[dict[str, Any]]:
        return await svc.list_policies(tenant_id=x_tenant_id, workspace_id=x_workspace_id)

    @router.get("/api/admin/memory/policies/{label}")
    async def get_policy(
        label: str,
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        svc: MemoryService = Depends(memory_dependency),  # noqa: B008
    ) -> dict[str, Any]:
        return await svc.get_policy(workspace_id=x_workspace_id, label=label)

    @router.get("/api/admin/memory/trend")
    async def trend(
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        range: str = Query(default="7d"),
        svc: MemoryService = Depends(memory_dependency),  # noqa: B008
    ) -> dict[str, list[int]]:
        return await svc.trend(workspace_id=x_workspace_id, range=range)

    return router
