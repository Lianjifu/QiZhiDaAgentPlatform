"""Domain ↔ ORM mappers for the platform module.

Pure functions; SQL repositories call these from inside the session.
"""

from __future__ import annotations

from decimal import Decimal

from qzdap_schema.ids import (
    PlanId,
    SubscriptionId,
    TenantId,
    TenantSettingId,
    UserId,
    WorkspaceId,
)

from qzdap.modules.platform.adapter.persistence.models import (
    PlanORM,
    SubscriptionORM,
    TenantSettingORM,
)
from qzdap.modules.platform.domain.entities import (
    Plan,
    Subscription,
    TenantSetting,
)
from qzdap.modules.platform.domain.value_objects import (
    PlanStatus,
    SubscriptionStatus,
)


def _to_decimal(value: object) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if value is None:
        return Decimal(0)
    return Decimal(str(value))


# ── Plan ──────────────────────────────────────────────────────────────────


def plan_to_domain(row: PlanORM) -> Plan:
    return Plan(
        id=PlanId(row.id),
        code=row.code,
        display_name=row.display_name,
        description=row.description or "",
        limits=dict(row.limits or {}),
        features=tuple(row.features or ()),
        price_monthly_usd=_to_decimal(row.price_monthly_usd),
        status=PlanStatus(row.status),
        sort_order=row.sort_order,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def plan_to_orm(entity: Plan) -> PlanORM:
    return PlanORM(
        id=entity.id,
        code=entity.code,
        display_name=entity.display_name,
        description=entity.description,
        limits=dict(entity.limits),
        features=list(entity.features),
        price_monthly_usd=entity.price_monthly_usd,
        status=entity.status.value,
        sort_order=entity.sort_order,
        created_at=entity.created_at,
        updated_at=entity.updated_at,
    )


# ── Subscription ──────────────────────────────────────────────────────────


def subscription_to_domain(row: SubscriptionORM) -> Subscription:
    return Subscription(
        id=SubscriptionId(row.id),
        tenant_id=TenantId(row.tenant_id),
        plan_id=PlanId(row.plan_id),
        plan_code=row.plan_code,
        status=SubscriptionStatus(row.status),
        started_at=row.started_at,
        ends_at=row.ends_at,
        auto_renew=row.auto_renew,
        updated_by=UserId(row.updated_by) if row.updated_by else None,
        created_at=row.created_at,
        updated_at=row.updated_at,
        metadata=dict(row.metadata_ or {}),
    )


def subscription_to_orm(entity: Subscription) -> SubscriptionORM:
    return SubscriptionORM(
        id=entity.id,
        tenant_id=entity.tenant_id,
        workspace_id=entity.workspace_id,
        plan_id=entity.plan_id,
        plan_code=entity.plan_code,
        status=entity.status.value,
        started_at=entity.started_at,
        ends_at=entity.ends_at,
        auto_renew=entity.auto_renew,
        updated_by=entity.updated_by,
        metadata_=dict(entity.metadata),
        created_at=entity.created_at,
        updated_at=entity.updated_at,
    )


# ── TenantSetting ────────────────────────────────────────────────────────


def tenant_setting_to_domain(row: TenantSettingORM) -> TenantSetting:
    return TenantSetting(
        id=TenantSettingId(row.id),
        tenant_id=TenantId(row.tenant_id),
        workspace_id=WorkspaceId(row.workspace_id) if row.workspace_id else None,
        key=row.key,
        value=row.value,
        updated_by=UserId(row.updated_by) if row.updated_by else None,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def tenant_setting_to_orm(entity: TenantSetting) -> TenantSettingORM:
    return TenantSettingORM(
        id=entity.id,
        tenant_id=entity.tenant_id,
        workspace_id=entity.workspace_id,
        key=entity.key,
        value=entity.value,
        updated_by=entity.updated_by,
        created_at=entity.created_at,
        updated_at=entity.updated_at,
    )


__all__ = [
    "plan_to_domain",
    "plan_to_orm",
    "subscription_to_domain",
    "subscription_to_orm",
    "tenant_setting_to_domain",
    "tenant_setting_to_orm",
]
