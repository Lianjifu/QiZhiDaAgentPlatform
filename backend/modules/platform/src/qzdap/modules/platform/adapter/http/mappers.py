"""Domain → DTO mappers for the platform module."""

from __future__ import annotations

from qzdap.modules.platform.adapter.http.dto import (
    PlanResponse,
    SubscriptionResponse,
    TenantSettingResponse,
)
from qzdap.modules.platform.domain.entities import (
    Plan,
    Subscription,
    TenantSetting,
)


def plan_to_dto(plan: Plan) -> PlanResponse:
    return PlanResponse(
        id=plan.id,
        code=plan.code,
        display_name=plan.display_name,
        description=plan.description,
        limits=dict(plan.limits),
        features=plan.features,
        price_monthly_usd=str(plan.price_monthly_usd),
        status=plan.status.value,
        sort_order=plan.sort_order,
        created_at=plan.created_at,
        updated_at=plan.updated_at,
    )


def subscription_to_dto(sub: Subscription) -> SubscriptionResponse:
    return SubscriptionResponse(
        id=sub.id,
        tenant_id=sub.tenant_id,
        plan_id=sub.plan_id,
        plan_code=sub.plan_code,
        status=sub.status.value,
        started_at=sub.started_at,
        ends_at=sub.ends_at,
        auto_renew=sub.auto_renew,
        updated_by=sub.updated_by,
        metadata=dict(sub.metadata),
        created_at=sub.created_at,
        updated_at=sub.updated_at,
    )


def tenant_setting_to_dto(setting: TenantSetting) -> TenantSettingResponse:
    return TenantSettingResponse(
        id=setting.id,
        tenant_id=setting.tenant_id,
        workspace_id=setting.workspace_id,
        key=setting.key,
        value=setting.value,
        updated_by=setting.updated_by,
        created_at=setting.created_at,
        updated_at=setting.updated_at,
    )


__all__ = [
    "plan_to_dto",
    "subscription_to_dto",
    "tenant_setting_to_dto",
]
