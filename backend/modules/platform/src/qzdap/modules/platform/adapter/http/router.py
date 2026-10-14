"""HTTP router for the platform module.

Mounts under ``/v1/platform``.  Per-request service is resolved
via :func:`platform_service_dependency`.

Endpoints (v1):

- GET  /v1/platform/plans                           → list Plans (catalog)
- GET  /v1/platform/subscriptions/me                → tenant's current sub
- PUT  /v1/platform/subscriptions/me                → assign/switch plan
- GET  /v1/platform/settings                        → list TenantSettings
- GET  /v1/platform/settings/{key}                  → read one setting
- PUT  /v1/platform/settings/{key}                  → upsert TenantSetting

Domain errors raised by use cases propagate as ``HTTPException`` via
the project's global exception handler on the FastAPI app.  Routes
that need a specific status mapping raise ``HTTPException`` directly.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from qzdap_kernel.errors import BusinessRuleError

from qzdap.modules.platform.adapter.http.dto import (
    AssignSubscriptionRequest,
    PlanListResponse,
    SubscriptionResponse,
    TenantSettingListResponse,
    TenantSettingResponse,
    UpsertSettingRequest,
)
from qzdap.modules.platform.adapter.http.factory import PlatformServiceFactory
from qzdap.modules.platform.adapter.http.mappers import (
    plan_to_dto,
    subscription_to_dto,
    tenant_setting_to_dto,
)
from qzdap.modules.platform.application.services import PlatformService
from qzdap.modules.platform.domain.errors import (
    PlanNotFound,
    TenantSettingNotFound,
)


async def platform_service_dependency(
    request: Request,
) -> PlatformService:
    factory: PlatformServiceFactory | None = getattr(
        request.app.state, "platform_service_factory", None
    )
    if factory is None:
        raise HTTPException(
            status_code=503,
            detail="platform service factory not wired",
        )
    return factory.for_session()


def build_router() -> APIRouter:
    router = APIRouter(prefix="/v1/platform", tags=["platform"])

    @router.get(
        "/plans",
        response_model=PlanListResponse,
    )
    async def list_plans(
        svc: PlatformService = Depends(platform_service_dependency),  # noqa: B008
        status: str | None = None,
    ) -> PlanListResponse:
        rows = await svc.list_plans(status=status)
        items = [plan_to_dto(p) for p in rows]
        return PlanListResponse(items=items, count=len(items))

    @router.get(
        "/subscriptions/me",
        response_model=SubscriptionResponse | None,
    )
    async def get_my_subscription(
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        svc: PlatformService = Depends(platform_service_dependency),  # noqa: B008
    ) -> SubscriptionResponse | None:
        from qzdap_schema.ids import TenantId

        sub = await svc.get_my_subscription(tenant_id=TenantId(x_tenant_id))
        if sub is None:
            return None
        return subscription_to_dto(sub)

    @router.put(
        "/subscriptions/me",
        response_model=SubscriptionResponse,
    )
    async def assign_my_subscription(
        body: AssignSubscriptionRequest,
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        x_user_id: UUID | None = Header(None, alias="X-User-Id"),  # noqa: B008
        svc: PlatformService = Depends(platform_service_dependency),  # noqa: B008
    ) -> SubscriptionResponse:
        from qzdap_schema.ids import TenantId, UserId

        try:
            sub = await svc.assign_subscription(
                tenant_id=TenantId(x_tenant_id),
                plan_code=body.plan_code,
                updated_by=UserId(x_user_id) if x_user_id else None,
                auto_renew=body.auto_renew,
            )
        except PlanNotFound as exc:
            raise HTTPException(status_code=404, detail=exc.code) from exc
        except BusinessRuleError as exc:
            raise HTTPException(status_code=422, detail=exc.code) from exc
        return subscription_to_dto(sub)

    @router.get(
        "/settings",
        response_model=TenantSettingListResponse,
    )
    async def list_settings(
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        svc: PlatformService = Depends(platform_service_dependency),  # noqa: B008
    ) -> TenantSettingListResponse:
        from qzdap_schema.ids import TenantId

        rows = await svc.list_settings(tenant_id=TenantId(x_tenant_id))
        items = [tenant_setting_to_dto(s) for s in rows]
        return TenantSettingListResponse(items=items, count=len(items))

    @router.put(
        "/settings/{key}",
        response_model=TenantSettingResponse,
    )
    async def upsert_setting(
        key: str,
        body: UpsertSettingRequest,
        request: Request,
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        x_user_id: UUID | None = Header(None, alias="X-User-Id"),  # noqa: B008
        svc: PlatformService = Depends(platform_service_dependency),  # noqa: B008
    ) -> TenantSettingResponse:
        from datetime import UTC, datetime
        from uuid import uuid4

        from qzdap.modules.identity.adapter.http.account_router import (
            actor,
            add_audit,
            control_session,
            current_user,
        )
        from sqlalchemy import select

        from qzdap.modules.platform.adapter.persistence.mappers import (
            tenant_setting_to_domain,
        )
        from qzdap.modules.platform.adapter.persistence.models import TenantSettingORM

        principal = actor(request)
        if not set(principal.roles) & {"admin", "platform_admin", "tenant_admin"}:
            raise HTTPException(403, "tenant administrator required")
        if body.workspace_id is not None:
            raise HTTPException(422, "platform settings are tenant-wide")
        async for session in control_session(request):
            user = await current_user(request, session)
            setting = await session.scalar(
                select(TenantSettingORM)
                .where(
                    TenantSettingORM.tenant_id == principal.tenant_id,
                    TenantSettingORM.key == key,
                )
                .with_for_update()
            )
            before = setting.value if setting else None
            if setting is None:
                setting = TenantSettingORM(
                    id=uuid4(),
                    tenant_id=principal.tenant_id,
                    workspace_id=None,
                    key=key,
                    value=body.value,
                    updated_by=user.id,
                )
                session.add(setting)
            else:
                setting.value = body.value
                setting.updated_by = user.id
                setting.updated_at = datetime.now(UTC)
            add_audit(
                session,
                request,
                user,
                None,
                f"platform.settings.{key}",
                {"key": key, "before": before, "after": body.value},
            )
            await session.flush()
            response = tenant_setting_to_dto(tenant_setting_to_domain(setting))
        return response

    @router.get(
        "/settings/{key}",
        response_model=TenantSettingResponse,
    )
    async def get_setting(
        key: str,
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        svc: PlatformService = Depends(platform_service_dependency),  # noqa: B008
    ) -> TenantSettingResponse:
        from qzdap_schema.ids import TenantId

        rows = await svc.list_settings(tenant_id=TenantId(x_tenant_id))
        match = next((s for s in rows if s.key == key), None)
        if match is None:
            raise HTTPException(
                status_code=404,
                detail=TenantSettingNotFound(f"setting {key!r} not found").code,
            )
        return tenant_setting_to_dto(match)

    return router


__all__ = ["build_router", "platform_service_dependency"]
