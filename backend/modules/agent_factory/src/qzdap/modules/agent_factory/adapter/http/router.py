"""HTTP router for the agent_factory module: templates + versions + releases.

Mounts under ``/v1/agents``.  Per-request service is resolved via
:func:`agent_factory_service_dependency`.

Endpoints (v1):

- POST   /v1/agents                              → create template
- GET    /v1/agents                              → list templates (workspace)
- GET    /v1/agents/{aid}                        → get template
- PATCH  /v1/agents/{aid}                        → update template
- POST   /v1/agents/{aid}/versions               → create draft version
- GET    /v1/agents/{aid}/versions               → list versions for template
- GET    /v1/agents/{aid}/versions/{vid}         → get version
- PATCH  /v1/agents/{aid}/versions/{vid}/notes   → update release_notes (draft only)
- POST   /v1/agents/{aid}/versions/{vid}/publish → publish (draft → published)
- POST   /v1/agents/{aid}/versions/{vid}/release → release (gate check, → released)
- POST   /v1/agents/{aid}/versions/{vid}/retire  → retire (released → retired)
- GET    /v1/agents/{aid}/versions/{vid}/releases → list releases for version's template
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from qzdap_kernel.errors import BusinessRuleError
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import ValidationError

from qzdap.modules.agent_factory.adapter.http.dto import (
    CreateTemplateRequest,
    CreateVersionRequest,
    ReleaseListResponse,
    ReleaseResponse,
    ReleaseVersionRequest,
    TemplateListResponse,
    TemplateResponse,
    UpdateTemplateRequest,
    UpdateVersionNotesRequest,
    VersionListResponse,
    VersionResponse,
)
from qzdap.modules.agent_factory.adapter.http.factory import (
    AgentFactoryServiceFactory,
)
from qzdap.modules.agent_factory.adapter.http.mappers import (
    release_to_dto,
    template_to_dto,
    version_to_dto,
)
from qzdap.modules.agent_factory.application.services import AgentFactoryService
from qzdap.modules.agent_factory.domain.errors import (
    AgentFactoryError,
    AgentTemplateNameConflict,
    AgentTemplateNotFound,
    AgentVersionImmutable,
    AgentVersionInvalidTransition,
    AgentVersionNotFound,
    AgentVersionTagConflict,
)


async def agent_factory_service_dependency(
    request: Request,
) -> AgentFactoryService:
    """Yield a per-request ``AgentFactoryService``.

    Production wires ``AgentFactoryServiceFactory`` via ``app.state``;
    when the factory is missing we surface 503.
    """
    factory: AgentFactoryServiceFactory | None = getattr(
        request.app.state, "agent_factory_service_factory", None
    )
    if factory is None:
        raise HTTPException(
            status_code=503,
            detail="agent_factory service factory not wired",
        )
    return factory.for_session()


# Phase 2: 把请求里的 default_model_id / model_id (上游名字符串) 解析成 UUID
# (admin_models.id). 走 lifespan 注册在 app.state.catalog_model_resolver 上的
# 短会话 Port; 不存在时为 None — 此时 allow 原始 str 写入, 由应用层 (chat
# resolver) 兜底 (向后兼容 Phase 1).
def _get_catalog_resolver(request: Request):
    return getattr(request.app.state, "catalog_model_resolver", None)


async def _resolve_model_uuid(
    request: Request,
    *,
    tenant_id: UUID,
    workspace_id: UUID,
    model: str | None,
) -> str | None:
    """Phase 2: 解析 helper. 接受 None / str / 已 UUID 形式, 返回 str (UUID) 或 None.

    - None → None (前端没传)
    - 已 UUID → 原样
    - str → 查 admin_models, 命中返回 str(UUID), 未命中 raise 422
    """
    if model is None or not str(model).strip():
        return None
    raw = str(model).strip()
    try:
        UUID(raw)
        return raw  # already UUID
    except (ValueError, TypeError, AttributeError):
        pass
    resolver = _get_catalog_resolver(request)
    if resolver is None:
        # 没注册就回退成 str (Phase 1 兼容, 让旧 agent 还能创建)
        return raw
    from qzdap_schema.ids import ModelId

    model_id: ModelId | None = await resolver.resolve(
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        upstream_model=raw,
    )
    if model_id is None:
        raise HTTPException(
            status_code=422,
            detail=(
                f"model_id '{raw}' not found in admin_models catalog. "
                "请先在 管理侧 → 模型管理 中添加该模型, 或选择 catalog 中已配置的模型."
            ),
        )
    return str(model_id)


def _domain_error_to_http(exc: Exception) -> HTTPException:
    if isinstance(exc, (AgentTemplateNotFound, AgentVersionNotFound)):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, (AgentTemplateNameConflict, AgentVersionTagConflict)):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, AgentVersionImmutable):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, AgentVersionInvalidTransition):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, BusinessRuleError):
        return HTTPException(status_code=exc.status, detail=str(exc))
    if isinstance(exc, AgentFactoryError):
        return HTTPException(status_code=400, detail=str(exc))
    return HTTPException(status_code=500, detail=str(exc))


def build_router() -> APIRouter:
    router = APIRouter(prefix="/v1/agents", tags=["agent_factory"])

    # ── templates ───────────────────────────────────────────────────────

    @router.post(
        "",
        status_code=201,
        response_model=TemplateResponse,
    )
    async def create_template(
        body: CreateTemplateRequest,
        request: Request,
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        x_user_id: UUID = Header(..., alias="X-User-Id"),  # noqa: B008
        svc: AgentFactoryService = Depends(agent_factory_service_dependency),  # noqa: B008
    ) -> TemplateResponse:
        from qzdap_schema.ids import TenantId, UserId, WorkspaceId

        # Phase 2: 解析 default_model_id str → UUID. 没命中 raise 422.
        resolved_default_model_id = await _resolve_model_uuid(
            request,
            tenant_id=x_tenant_id,
            workspace_id=x_workspace_id,
            model=body.default_model_id,
        )
        try:
            template = await svc.create_template.execute(  # type: ignore[union-attr]
                tenant_id=TenantId(x_tenant_id),
                workspace_id=WorkspaceId(x_workspace_id),
                name=body.name,
                description=body.description,
                default_model_id=resolved_default_model_id,
                default_system_prompt=body.default_system_prompt,
                metadata=body.metadata,
                created_by=UserId(x_user_id),
            )
        except (ValueError, ValidationError) as exc:
            raise HTTPException(status_code=422, detail=str(exc))
        except Exception as exc:  # noqa: BLE001
            raise _domain_error_to_http(exc)
        return template_to_dto(template)

    @router.get(
        "",
        response_model=TemplateListResponse,
    )
    async def list_templates(
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        svc: AgentFactoryService = Depends(agent_factory_service_dependency),  # noqa: B008
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
    ) -> TemplateListResponse:
        from qzdap_schema.ids import TenantId, WorkspaceId

        rows = await svc.list_templates.execute(  # type: ignore[union-attr]
            tenant_id=TenantId(x_tenant_id),
            workspace_id=WorkspaceId(x_workspace_id),
            limit=limit,
            offset=offset,
        )
        return TemplateListResponse(
            items=[template_to_dto(r) for r in rows],
            count=len(rows),
        )

    @router.get(
        "/{aid}",
        response_model=TemplateResponse,
    )
    async def get_template(
        aid: UUID,
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        svc: AgentFactoryService = Depends(agent_factory_service_dependency),  # noqa: B008
    ) -> TemplateResponse:
        from qzdap_schema.ids import AgentTemplateId, TenantId

        try:
            template = await svc.get_template.execute(  # type: ignore[union-attr]
                tenant_id=TenantId(x_tenant_id),
                template_id=AgentTemplateId(aid),
            )
        except Exception as exc:  # noqa: BLE001
            raise _domain_error_to_http(exc)
        return template_to_dto(template)

    @router.patch(
        "/{aid}",
        response_model=TemplateResponse,
    )
    async def update_template(
        aid: UUID,
        body: UpdateTemplateRequest,
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        svc: AgentFactoryService = Depends(agent_factory_service_dependency),  # noqa: B008
    ) -> TemplateResponse:
        from qzdap_schema.ids import AgentTemplateId, TenantId

        from qzdap.modules.agent_factory.domain.value_objects import AgentTemplateStatus

        if body.status is None:
            raise HTTPException(status_code=422, detail="status is required")
        try:
            new_status = AgentTemplateStatus(body.status)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
        try:
            template = await svc.update_template.execute(  # type: ignore[union-attr]
                tenant_id=TenantId(x_tenant_id),
                template_id=AgentTemplateId(aid),
                status=new_status,
            )
        except Exception as exc:  # noqa: BLE001
            raise _domain_error_to_http(exc)
        return template_to_dto(template)

    # ── versions ────────────────────────────────────────────────────────

    @router.get(
        "/options/models",
        response_model=list[dict[str, Any]],
    )
    async def list_model_options(
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        request: Request = ...,  # type: ignore[assignment]
    ) -> list[dict[str, Any]]:
        """Phase 2: 给 agent 创建/编辑表单提供「模型」下拉数据.

        列 workspace 内所有 status='active' 的 admin_models, 字段:
        {id, name, upstream_model, provider_name, context_window, status, tier}.

        Resolver 注册在 app.state.catalog_model_resolver; 没注册就回空列表.
        """
        from sqlalchemy import select

        from qzdap.modules.model.adapter.persistence.models import (
            CatalogModelORM,
        )

        resolver = _get_catalog_resolver(request)
        if resolver is None:
            return []
        try:
            sf = resolver._sf  # noqa: SLF001 — 同 package 内访问
            async with sf.session() as session:
                result = await session.execute(
                    select(
                        CatalogModelORM.id,
                        CatalogModelORM.name,
                        CatalogModelORM.upstream_model,
                        CatalogModelORM.provider_name,
                        CatalogModelORM.context_window,
                        CatalogModelORM.status,
                        CatalogModelORM.tier,
                    ).where(
                        CatalogModelORM.tenant_id == x_tenant_id,
                        CatalogModelORM.workspace_id == x_workspace_id,
                        CatalogModelORM.status == "active",
                    ).order_by(CatalogModelORM.name.asc())
                )
                rows = result.all()
            return [
                {
                    "id": str(r.id),
                    "name": r.name,
                    "upstream_model": r.upstream_model,
                    "provider_name": r.provider_name,
                    "context_window": int(r.context_window),
                    "status": r.status,
                    "tier": r.tier,
                }
                for r in rows
            ]
        except Exception:  # pragma: no cover - defensive
            return []

    @router.get(
        "/options/routes",
        response_model=list[dict[str, Any]],
    )
    async def list_route_options(
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        request: Request = ...,  # type: ignore[assignment]
    ) -> list[dict[str, Any]]:
        """Phase 15: 给 agent 创建/编辑表单提供「策略路由」下拉数据.

        列 workspace 内所有 enabled=true 的 admin_model_routes, 字段:
        {id, name, strategy, primary_model_id, fallback_model_ids, task,
         description, enabled}.

        Resolver 注册在 app.state.catalog_model_resolver; 没注册就回空列表.
        """
        from sqlalchemy import select

        from qzdap.modules.model.adapter.persistence.models import (
            RouteORM,
        )

        resolver = _get_catalog_resolver(request)
        if resolver is None:
            return []
        try:
            sf = resolver._sf  # noqa: SLF001 — 同 package 内访问
            async with sf.session() as session:
                result = await session.execute(
                    select(
                        RouteORM.id,
                        RouteORM.name,
                        RouteORM.strategy,
                        RouteORM.task,
                        RouteORM.priority,
                        RouteORM.primary_model_id,
                        RouteORM.fallback_model_ids,
                        RouteORM.description,
                        RouteORM.enabled,
                    ).where(
                        RouteORM.tenant_id == x_tenant_id,
                        RouteORM.workspace_id == x_workspace_id,
                        RouteORM.enabled.is_(True),
                    ).order_by(RouteORM.priority.desc(), RouteORM.name.asc())
                )
                rows = result.all()
            return [
                {
                    "id": str(r.id),
                    "name": r.name,
                    "strategy": r.strategy,
                    "task": r.task,
                    "priority": int(r.priority),
                    "primary_model_id": str(r.primary_model_id),
                    "fallback_model_ids": [
                        str(mid) for mid in (r.fallback_model_ids or [])
                    ],
                    "description": r.description,
                    "enabled": bool(r.enabled),
                }
                for r in rows
            ]
        except Exception:  # pragma: no cover - defensive
            return []

    @router.post(
        "/{aid}/versions",
        status_code=201,
        response_model=VersionResponse,
    )
    async def create_version(
        aid: UUID,
        body: CreateVersionRequest,
        request: Request,
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        x_user_id: UUID = Header(..., alias="X-User-Id"),  # noqa: B008
        svc: AgentFactoryService = Depends(agent_factory_service_dependency),  # noqa: B008
    ) -> VersionResponse:
        from qzdap_schema.ids import AgentTemplateId, TenantId, UserId, WorkspaceId

        # Phase 2: 解析 model_id str → UUID. 没命中 raise 422.
        resolved_model_id = await _resolve_model_uuid(
            request,
            tenant_id=x_tenant_id,
            workspace_id=x_workspace_id,
            model=body.model_id,
        )
        # Phase 15: 解析 route_id str → UUID. 没命中 422.
        resolved_route_id: UUID | None = None
        if body.route_id:
            try:
                resolved_route_id = UUID(str(body.route_id))
            except (ValueError, TypeError) as exc:
                raise HTTPException(
                    status_code=422,
                    detail=f"route_id 不是有效 UUID: {body.route_id!r}",
                ) from exc
        try:
            version = await svc.create_version.execute(  # type: ignore[union-attr]
                tenant_id=TenantId(x_tenant_id),
                workspace_id=WorkspaceId(x_workspace_id),
                template_id=AgentTemplateId(aid),
                version_tag=body.version_tag,
                system_prompt=body.system_prompt,
                model_id=resolved_model_id,
                route_id=resolved_route_id,
                route_strategy=body.route_strategy,
                allowed_tools=tuple(body.allowed_tools),
                allowed_skills=tuple(body.allowed_skills),
                knowledge_package_ids=tuple(body.knowledge_package_ids),
                plan_dsl_snapshot=body.plan_dsl_snapshot,
                max_total_steps=body.max_total_steps,
                release_notes=body.release_notes,
                metadata=body.metadata,
                created_by=UserId(x_user_id),
            )
        except (ValueError, ValidationError) as exc:
            raise HTTPException(status_code=422, detail=str(exc))
        except Exception as exc:  # noqa: BLE001
            raise _domain_error_to_http(exc)
        return version_to_dto(version)

    @router.get(
        "/{aid}/versions",
        response_model=VersionListResponse,
    )
    async def list_versions(
        aid: UUID,
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        svc: AgentFactoryService = Depends(agent_factory_service_dependency),  # noqa: B008
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
    ) -> VersionListResponse:
        from qzdap_schema.ids import AgentTemplateId, TenantId

        rows = await svc.list_versions.execute(  # type: ignore[union-attr]
            tenant_id=TenantId(x_tenant_id),
            template_id=AgentTemplateId(aid),
            limit=limit,
            offset=offset,
        )
        return VersionListResponse(
            items=[version_to_dto(r) for r in rows],
            count=len(rows),
        )

    @router.get(
        "/{aid}/versions/{vid}",
        response_model=VersionResponse,
    )
    async def get_version(
        aid: UUID,
        vid: UUID,
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        svc: AgentFactoryService = Depends(agent_factory_service_dependency),  # noqa: B008
    ) -> VersionResponse:
        from qzdap_schema.ids import AgentVersionId, TenantId

        try:
            version = await svc.get_version.execute(  # type: ignore[union-attr]
                tenant_id=TenantId(x_tenant_id),
                version_id=AgentVersionId(vid),
            )
        except Exception as exc:  # noqa: BLE001
            raise _domain_error_to_http(exc)
        return version_to_dto(version)

    @router.patch(
        "/{aid}/versions/{vid}/notes",
        response_model=VersionResponse,
    )
    async def update_version_notes(
        aid: UUID,
        vid: UUID,
        body: UpdateVersionNotesRequest,
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        svc: AgentFactoryService = Depends(agent_factory_service_dependency),  # noqa: B008
    ) -> VersionResponse:
        from qzdap_schema.ids import AgentVersionId, TenantId

        try:
            version = await svc.update_version_notes.execute(  # type: ignore[union-attr]
                tenant_id=TenantId(x_tenant_id),
                version_id=AgentVersionId(vid),
                release_notes=body.release_notes,
            )
        except (ValueError, ValidationError) as exc:
            raise HTTPException(status_code=422, detail=str(exc))
        except Exception as exc:  # noqa: BLE001
            raise _domain_error_to_http(exc)
        return version_to_dto(version)

    @router.post(
        "/{aid}/versions/{vid}/publish",
        response_model=VersionResponse,
    )
    async def publish_version(
        aid: UUID,
        vid: UUID,
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        svc: AgentFactoryService = Depends(agent_factory_service_dependency),  # noqa: B008
    ) -> VersionResponse:
        from qzdap_schema.ids import AgentVersionId, TenantId

        try:
            version = await svc.publish_version.execute(  # type: ignore[union-attr]
                tenant_id=TenantId(x_tenant_id),
                version_id=AgentVersionId(vid),
            )
        except Exception as exc:  # noqa: BLE001
            raise _domain_error_to_http(exc)
        return version_to_dto(version)

    @router.post(
        "/{aid}/versions/{vid}/release",
        response_model=ReleaseResponse,
    )
    async def release_version(
        aid: UUID,
        vid: UUID,
        body: ReleaseVersionRequest | None = None,
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        x_user_id: UUID = Header(..., alias="X-User-Id"),  # noqa: B008
        svc: AgentFactoryService = Depends(agent_factory_service_dependency),  # noqa: B008
    ) -> ReleaseResponse:
        from qzdap_schema.ids import (
            AgentTemplateId,
            AgentVersionId,
            TenantId,
            UserId,
            WorkspaceId,
        )

        notes = body.notes if body else ""
        try:
            release = await svc.release_version.execute(  # type: ignore[union-attr]
                tenant_id=TenantId(x_tenant_id),
                workspace_id=WorkspaceId(x_workspace_id),
                template_id=AgentTemplateId(aid),
                version_id=AgentVersionId(vid),
                released_by=UserId(x_user_id),
                notes=notes,
            )
        except Exception as exc:  # noqa: BLE001
            raise _domain_error_to_http(exc)
        return release_to_dto(release)

    @router.post(
        "/{aid}/versions/{vid}/retire",
        response_model=VersionResponse,
    )
    async def retire_version(
        aid: UUID,
        vid: UUID,
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        svc: AgentFactoryService = Depends(agent_factory_service_dependency),  # noqa: B008
    ) -> VersionResponse:
        from qzdap_schema.ids import AgentVersionId, TenantId

        try:
            version = await svc.retire_version.execute(  # type: ignore[union-attr]
                tenant_id=TenantId(x_tenant_id),
                version_id=AgentVersionId(vid),
            )
        except Exception as exc:  # noqa: BLE001
            raise _domain_error_to_http(exc)
        return version_to_dto(version)

    @router.get(
        "/{aid}/versions/{vid}/releases",
        response_model=ReleaseListResponse,
    )
    async def list_releases(
        aid: UUID,
        vid: UUID,
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        svc: AgentFactoryService = Depends(agent_factory_service_dependency),  # noqa: B008
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
    ) -> ReleaseListResponse:
        from qzdap_schema.ids import AgentTemplateId, TenantId

        rows = await svc.list_releases.execute(  # type: ignore[union-attr]
            tenant_id=TenantId(x_tenant_id),
            template_id=AgentTemplateId(aid),
            limit=limit,
            offset=offset,
        )
        return ReleaseListResponse(
            items=[release_to_dto(r) for r in rows],
            count=len(rows),
        )

    return router


__all__ = ["agent_factory_service_dependency", "build_router"]
