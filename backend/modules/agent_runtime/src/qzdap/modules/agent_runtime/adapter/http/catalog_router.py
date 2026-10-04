"""HTTP adapter for admin agents + user catalog."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request

from qzdap.modules.agent_runtime.application.catalog import AgentCatalogService


def _owner_id(request: Request, fallback: UUID) -> UUID:
    principal = getattr(request.state, "principal", None)
    pid = getattr(principal, "id", None)
    if pid is None:
        return fallback
    return UUID(str(pid))


async def catalog_dependency(request: Request) -> AgentCatalogService:
    factory = getattr(request.app.state, "agent_catalog_factory", None)
    container = getattr(request.app.state, "container", None)
    if factory is None or container is None:
        raise HTTPException(status_code=503, detail="agent catalog factory not wired")
    sf = container.session_factory()
    async with sf.session() as session:
        svc = factory.for_session(session)
        try:
            yield svc
        except Exception:
            await session.rollback()
            raise
        await session.commit()


def build_catalog_router() -> APIRouter:
    router = APIRouter(tags=["agents"])

    @router.get("/api/admin/agents")
    async def list_admin_agents(
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        search: str = Query(default=""),
        tab: str = Query(default="all"),
        sortKey: str = Query(default="updated"),
        svc: AgentCatalogService = Depends(catalog_dependency),  # noqa: B008
    ) -> list[dict[str, Any]]:
        return await svc.list_admin(
            workspace_id=x_workspace_id, search=search, tab=tab, sort_key=sortKey
        )

    @router.post("/api/admin/agents", status_code=201)
    async def create_admin_agent(
        body: dict[str, Any],
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        svc: AgentCatalogService = Depends(catalog_dependency),  # noqa: B008
    ) -> dict[str, Any]:
        return await svc.create(tenant_id=x_tenant_id, workspace_id=x_workspace_id, body=body)

    @router.get("/api/admin/agents/{agent_id}")
    async def get_admin_agent(
        agent_id: UUID,
        svc: AgentCatalogService = Depends(catalog_dependency),  # noqa: B008
    ) -> dict[str, Any]:
        return await svc.get_admin(agent_id)

    @router.patch("/api/admin/agents/{agent_id}")
    async def patch_admin_agent(
        agent_id: UUID,
        body: dict[str, Any],
        svc: AgentCatalogService = Depends(catalog_dependency),  # noqa: B008
    ) -> dict[str, Any]:
        return await svc.update(agent_id=agent_id, body=body)

    @router.delete("/api/admin/agents/{agent_id}")
    async def delete_admin_agent(
        agent_id: UUID,
        svc: AgentCatalogService = Depends(catalog_dependency),  # noqa: B008
    ) -> dict[str, Any]:
        return await svc.delete(agent_id)

    @router.get("/api/admin/agents/{agent_id}/versions")
    async def agent_versions(
        agent_id: UUID,
        svc: AgentCatalogService = Depends(catalog_dependency),  # noqa: B008
    ) -> dict[str, Any]:
        return await svc.versions(agent_id)

    @router.get("/api/admin/agents/{agent_id}/evaluations")
    async def agent_evaluations(
        agent_id: UUID,
        svc: AgentCatalogService = Depends(catalog_dependency),  # noqa: B008
    ) -> dict[str, Any]:
        return await svc.evaluations(agent_id)

    @router.post("/api/admin/agents/{agent_id}/star")
    async def star_agent(
        agent_id: UUID,
        body: dict[str, Any],
        svc: AgentCatalogService = Depends(catalog_dependency),  # noqa: B008
    ) -> dict[str, Any]:
        return await svc.star(agent_id, bool(body.get("starred", True)))

    @router.post("/api/admin/agents/{agent_id}/eval")
    async def eval_agent(
        agent_id: UUID,
        svc: AgentCatalogService = Depends(catalog_dependency),  # noqa: B008
    ) -> dict[str, Any]:
        return await svc.run_eval(agent_id)

    @router.delete("/api/admin/agents/bulk-delete")
    async def bulk_delete(
        body: dict[str, Any],
        svc: AgentCatalogService = Depends(catalog_dependency),  # noqa: B008
    ) -> dict[str, Any]:
        return await svc.bulk_delete([str(item) for item in (body.get("ids") or [])])

    @router.post("/api/admin/agents/batch-status")
    async def batch_status(
        body: dict[str, Any],
        svc: AgentCatalogService = Depends(catalog_dependency),  # noqa: B008
    ) -> dict[str, Any]:
        return await svc.batch_status(
            ids=[str(item) for item in (body.get("ids") or [])],
            status=str(body.get("status") or "published"),
        )

    @router.post("/api/admin/agents/diff")
    async def diff_agents(
        body: dict[str, Any],
        svc: AgentCatalogService = Depends(catalog_dependency),  # noqa: B008
    ) -> dict[str, Any]:
        return await svc.diff(
            agent_id=UUID(str(body.get("agentId"))),
            left_version=str(body.get("leftVersion") or ""),
            right_version=str(body.get("rightVersion") or ""),
        )

    @router.post("/api/admin/agents/import")
    async def import_agents(
        body: dict[str, Any],
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        svc: AgentCatalogService = Depends(catalog_dependency),  # noqa: B008
    ) -> dict[str, Any]:
        created = 0
        for row in body.get("rows") or []:
            source = row.get("source") if isinstance(row, dict) else None
            if not isinstance(source, dict):
                continue
            await svc.create(tenant_id=x_tenant_id, workspace_id=x_workspace_id, body=source)
            created += 1
        return {"created": created}

    @router.post("/api/admin/agents/export")
    async def export_agents(
        body: dict[str, Any],
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        svc: AgentCatalogService = Depends(catalog_dependency),  # noqa: B008
    ) -> dict[str, Any]:
        items = await svc.list_admin(workspace_id=x_workspace_id)
        _ = body
        return {"url": "", "count": len(items)}

    @router.get("/api/catalog/agents")
    async def list_catalog_agents(
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        svc: AgentCatalogService = Depends(catalog_dependency),  # noqa: B008
    ) -> list[dict[str, Any]]:
        return await svc.list_catalog(workspace_id=x_workspace_id)

    @router.post("/api/catalog/agents/{agent_id}/favorite")
    async def favorite_agent(
        agent_id: UUID,
        body: dict[str, Any],
        request: Request,
        x_user_id: UUID = Header(default=UUID(int=0), alias="X-User-Id"),  # noqa: B008
        svc: AgentCatalogService = Depends(catalog_dependency),  # noqa: B008
    ) -> dict[str, Any]:
        user_id = _owner_id(request, x_user_id)
        return await svc.set_favorite(agent_id=agent_id, user_id=user_id, on=bool(body.get("on")))

    return router


__all__ = ["build_catalog_router"]
