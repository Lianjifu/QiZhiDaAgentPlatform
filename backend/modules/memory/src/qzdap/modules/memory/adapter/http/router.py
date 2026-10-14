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


async def _related_agents(
    request: Request, workspace_id: UUID, predicate: Any
) -> list[dict[str, Any]]:
    factory = getattr(request.app.state, "agent_catalog_factory", None)
    container = getattr(request.app.state, "container", None)
    if factory is None or container is None:
        raise HTTPException(status_code=503, detail="agent catalog factory not wired")
    async with container.session_factory().session() as session:
        service = factory.for_session(session)
        principal = getattr(request.state, "principal", None)
        if principal:
            service.bind_scope(
                tenant_id=principal.tenant_id, workspace_id=principal.workspace_id
            )
        agents = await service.list_admin(workspace_id=workspace_id)
        return [agent for agent in agents if predicate(agent)]


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
        return await svc.list_policies(
            tenant_id=x_tenant_id, workspace_id=x_workspace_id
        )

    @router.get("/api/admin/memory/policies/{label}")
    async def get_policy(
        label: str,
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        svc: MemoryService = Depends(memory_dependency),  # noqa: B008
    ) -> dict[str, Any]:
        return await svc.get_policy(workspace_id=x_workspace_id, label=label)

    @router.get("/api/admin/memory/policies/{label}/agents")
    async def policy_agents(
        label: str,
        request: Request,
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        svc: MemoryService = Depends(memory_dependency),
    ) -> list[dict[str, Any]]:  # noqa: B008
        policy = await svc.get_policy(workspace_id=x_workspace_id, label=label)
        scope = {"l1": "session", "l2": "user", "l3": "tenant"}[policy["layer"]]
        return await _related_agents(
            request,
            x_workspace_id,
            lambda agent: (
                agent["memoryPolicy"].get("enabled") is True
                and (
                    agent["memoryPolicy"].get("policyLabel") == label
                    or agent["memoryPolicy"].get("scope") == scope
                )
            ),
        )

    @router.get("/api/admin/memory/l3/{item_id}/agents")
    async def l3_agents(
        item_id: UUID,
        request: Request,
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        svc: MemoryService = Depends(memory_dependency),
    ) -> list[dict[str, Any]]:  # noqa: B008
        entry = await svc._catalog.get_l3(item_id)
        if entry is None or entry.workspace_id != x_workspace_id:
            raise HTTPException(status_code=404, detail="memory entry not found")
        target = str(item_id)
        return await _related_agents(
            request,
            x_workspace_id,
            lambda agent: (
                target in (agent["memoryPolicy"].get("l3EntryIds") or [])
                or any(
                    ref.get("id") == target and ref.get("type") in {"memory", "l3"}
                    for ref in agent["knowledgeRefs"]
                )
            ),
        )

    @router.get("/api/admin/memory/trend")
    async def trend(
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        range: str = Query(default="7d"),
        svc: MemoryService = Depends(memory_dependency),  # noqa: B008
    ) -> dict[str, list[int]]:
        return await svc.trend(workspace_id=x_workspace_id, range=range)

    return router
