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


async def require_model_admin(
    request: Request,
    x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
    x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
) -> Any:
    principal = getattr(request.state, "principal", None)
    if principal is None:
        raise HTTPException(status_code=401, detail="authentication required")
    if not set(principal.roles).intersection(
        {"admin", "platform_admin", "workspace_owner"}
    ):
        raise HTTPException(status_code=403, detail="admin required")
    if principal.tenant_id != x_tenant_id or principal.workspace_id != x_workspace_id:
        raise HTTPException(status_code=403, detail="scope mismatch")
    return principal


async def model_dependency(
    request: Request,
    principal: Any = Depends(require_model_admin),  # noqa: B008
) -> ModelService:
    factory = getattr(request.app.state, "model_service_factory", None)
    container = getattr(request.app.state, "container", None)
    if factory is None or container is None:
        raise HTTPException(status_code=503, detail="model factory not wired")
    sf = container.session_factory()
    async with sf.session() as session:
        svc = factory.for_session(session)
        svc.bind_scope(
            tenant_id=principal.tenant_id,
            workspace_id=principal.workspace_id,
            actor_id=principal.id,
            actor_name=principal.display_name,
        )
        try:
            yield svc
        except Exception as exc:
            await session.rollback()
            from qzdap.modules.model.domain.errors import (
                CredentialNotFound,
                ModelNotFound,
                RouteNotFound,
            )

            if isinstance(exc, (ModelNotFound, RouteNotFound)):
                raise HTTPException(status_code=404, detail="not found") from exc
            if isinstance(exc, (ValueError, CredentialNotFound)):
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            if isinstance(exc, PermissionError):
                raise HTTPException(status_code=403, detail="scope mismatch") from exc
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
        svc: ModelService = Depends(model_dependency),  # noqa: B008  # noqa: B008
    ) -> list[dict[str, Any]]:
        return await svc.list_models(
            workspace_id=x_workspace_id, search=search, status=status, tier=tier
        )

    @router.get("/api/admin/models/providers")
    async def list_admin_providers(
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        svc: ModelService = Depends(model_dependency),  # noqa: B008  # noqa: B008
    ) -> list[dict[str, Any]]:
        return await svc.list_providers(workspace_id=x_workspace_id)

    @router.get("/api/admin/models/routes")
    async def list_admin_routes(
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        svc: ModelService = Depends(model_dependency),  # noqa: B008  # noqa: B008
    ) -> list[dict[str, Any]]:
        return await svc.list_routes(workspace_id=x_workspace_id)

    @router.get("/api/admin/models/health")
    async def list_admin_health(
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        svc: ModelService = Depends(model_dependency),  # noqa: B008  # noqa: B008
    ) -> list[dict[str, Any]]:
        return await svc.list_health(workspace_id=x_workspace_id)

    @router.get("/api/admin/llm/audit")
    async def list_llm_audit(
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
        model_id: UUID | None = Query(default=None),
        event_type: str | None = Query(default=None, description="llm.invoke / llm.invoke.failed"),
        actor_id: UUID | None = Query(default=None),
        since: str | None = Query(
            default=None, description="ISO timestamp, e.g. 2026-10-17T00:00:00Z"
        ),
        svc: ModelService = Depends(model_dependency),  # noqa: B008
    ) -> dict[str, Any]:
        """Phase 11: LLM 审计日志查询. 直接读 audit_log (governance 表).

        过滤: tenant_id (强制, 防越权), 可选 model_id / actor_id / event_type / since.
        返回: {items, count, total}. items 含 payload (error_class / latency_ms 等).
        """
        from sqlalchemy import text

        params: dict[str, Any] = {
            "tenant_id": str(x_tenant_id),
            "limit": limit,
            "offset": offset,
        }
        where = [
            "tenant_id = :tenant_id",
            "event_type LIKE 'llm.%'",
        ]
        if model_id is not None:
            where.append("payload->>'model_id' = :model_id")
            params["model_id"] = str(model_id)
        if event_type is not None:
            where.append("event_type = :event_type")
            params["event_type"] = event_type
        if actor_id is not None:
            where.append("actor_id = :actor_id")
            params["actor_id"] = str(actor_id)
        if since is not None:
            where.append("created_at >= :since")
            params["since"] = since

        where_sql = " AND ".join(where)
        list_sql = text(
            f"SELECT id, tenant_id, actor_id, event_type, payload, created_at, updated_at "
            f"FROM audit_log WHERE {where_sql} "
            f"ORDER BY created_at DESC LIMIT :limit OFFSET :offset"
        )
        count_sql = text(f"SELECT count(*) FROM audit_log WHERE {where_sql}")
        # 强制使用 model module 自己的 session, 不破坏 audit_log 跨模块责任
        session = svc._models._s  # type: ignore[attr-defined]
        list_result = await session.execute(list_sql, params)
        count_result = await session.execute(count_sql, params)
        items = [
            {
                "id": str(r.id),
                "tenant_id": str(r.tenant_id),
                "actor_id": str(r.actor_id) if r.actor_id else None,
                "event_type": r.event_type,
                "payload": r.payload,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in list_result.fetchall()
        ]
        return {
            "items": items,
            "count": len(items),
            "total": int(count_result.scalar() or 0),
        }

    @router.post("/api/admin/models/providers/{provider_id}/health-check")
    async def provider_health_check(
        provider_id: UUID, svc: ModelService = Depends(model_dependency)
    ) -> dict[str, Any]:
        return await svc.health_check(provider_id)

    @router.post("/api/admin/models/import")
    async def import_models(
        body: dict[str, Any],
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),
        svc: ModelService = Depends(model_dependency),
    ) -> dict[str, Any]:
        return await svc.import_models(
            tenant_id=x_tenant_id, workspace_id=x_workspace_id, body=body
        )

    @router.post("/api/admin/models/catalog")
    async def probe_catalog(
        body: dict[str, Any],
        svc: ModelService = Depends(model_dependency),  # noqa: B008  # noqa: B008
    ) -> dict[str, Any]:
        return await svc.probe_catalog(body)

    @router.post("/api/admin/models/connectivity-test")
    async def test_connectivity(
        body: dict[str, Any],
        svc: ModelService = Depends(model_dependency),  # noqa: B008
    ) -> dict[str, Any]:
        return await svc.test_connectivity(body)

    @router.post("/api/admin/models", status_code=201)
    async def create_admin_models(
        body: dict[str, Any],
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        svc: ModelService = Depends(model_dependency),  # noqa: B008  # noqa: B008
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
        svc: ModelService = Depends(model_dependency),  # noqa: B008  # noqa: B008
    ) -> dict[str, Any]:
        return await svc.create_route(
            tenant_id=x_tenant_id, workspace_id=x_workspace_id, body=body
        )

    @router.post("/api/admin/models/batch-status")
    async def batch_admin_status(
        body: dict[str, Any],
        svc: ModelService = Depends(model_dependency),  # noqa: B008  # noqa: B008
    ) -> dict[str, Any]:
        return await svc.batch_status(
            ids=[str(item) for item in (body.get("ids") or [])],
            status=str(body.get("status") or "draft"),
        )

    @router.get("/api/admin/models/{model_id}")
    async def get_admin_model(
        model_id: UUID,
        svc: ModelService = Depends(model_dependency),  # noqa: B008  # noqa: B008
    ) -> dict[str, Any]:
        return await svc.get_model(model_id)

    @router.patch("/api/admin/models/{model_id}")
    async def patch_admin_model(
        model_id: UUID,
        body: dict[str, Any],
        svc: ModelService = Depends(model_dependency),  # noqa: B008  # noqa: B008
    ) -> dict[str, Any]:
        return await svc.update_model(model_id=model_id, body=body)

    @router.delete("/api/admin/models/{model_id}")
    async def delete_admin_model(
        model_id: UUID,
        svc: ModelService = Depends(model_dependency),  # noqa: B008  # noqa: B008
    ) -> dict[str, Any]:
        return await svc.delete_model(model_id)

    @router.post("/api/admin/models/{model_id}/star")
    async def star_admin_model(
        model_id: UUID,
        body: dict[str, Any],
        svc: ModelService = Depends(model_dependency),  # noqa: B008  # noqa: B008
    ) -> dict[str, Any]:
        return await svc.set_starred(
            model_id=model_id, starred=bool(body.get("starred"))
        )

    @router.post("/api/admin/models/routes/{route_id}/toggle")
    async def toggle_admin_route(
        route_id: UUID,
        svc: ModelService = Depends(model_dependency),  # noqa: B008  # noqa: B008
    ) -> dict[str, Any]:
        return await svc.toggle_route(route_id)

    @router.delete("/api/admin/models/routes/{route_id}")
    async def delete_admin_route(
        route_id: UUID,
        svc: ModelService = Depends(model_dependency),  # noqa: B008  # noqa: B008
    ) -> dict[str, Any]:
        return await svc.delete_route(route_id)

    @router.get("/api/admin/models/routes/{route_id}/preview-chain")
    async def preview_route_chain(
        route_id: UUID,
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        svc: ModelService = Depends(model_dependency),  # noqa: B008
    ) -> dict[str, Any]:
        """Phase 16: 预览 route 解析后的 model chain (不发请求, 不消耗 quota).

        返回: {routeId, routeName, strategy, primaryModelId, chain: [{id, name,
        upstreamModel, tier, successRate, latencyMs, isPrimary}, ...]}
        """
        return await svc.preview_chain(
            tenant_id=x_tenant_id,
            workspace_id=x_workspace_id,
            route_id=route_id,
        )

    # ── Phase 17: quota admin CRUD + usage ────────────────────────────────

    @router.get("/api/admin/models/quotas")
    async def list_admin_quotas(
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        svc: ModelService = Depends(model_dependency),  # noqa: B008
    ) -> list[dict[str, Any]]:
        return await svc.list_quotas(
            tenant_id=x_tenant_id, workspace_id=x_workspace_id
        )

    @router.post("/api/admin/models/quotas", status_code=201)
    async def upsert_admin_quota(
        body: dict[str, Any],
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        svc: ModelService = Depends(model_dependency),  # noqa: B008
    ) -> dict[str, Any]:
        try:
            return await svc.upsert_quota(
                tenant_id=x_tenant_id,
                workspace_id=x_workspace_id,
                body=body,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.delete("/api/admin/models/quotas/{quota_id}")
    async def delete_admin_quota(
        quota_id: UUID,
        svc: ModelService = Depends(model_dependency),  # noqa: B008
    ) -> dict[str, Any]:
        await svc.delete_quota(quota_id=quota_id)
        return {"ok": True, "id": str(quota_id)}

    @router.get("/api/admin/models/quotas/usage")
    async def list_admin_quota_usage(
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        svc: ModelService = Depends(model_dependency),  # noqa: B008
    ) -> list[dict[str, Any]]:
        return await svc.list_usage(
            tenant_id=x_tenant_id, workspace_id=x_workspace_id
        )

    return router
