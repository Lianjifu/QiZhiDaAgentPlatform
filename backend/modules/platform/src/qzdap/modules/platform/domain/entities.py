"""Platform domain entities.

Three aggregate roots:

- :class:`Plan` — global catalog row.  One per ``code``.  Mutable
  ``status`` (active ↔ hidden ↔ retired); ``code`` is immutable once
  created.  ``limits`` is JSONB dict; ``features`` is an ordered tuple
  of feature strings.
- :class:`Subscription` — per-tenant assignment to a :class:`Plan`.
  One per tenant (uniqueness enforced at the SQL layer).  Mutable
  ``plan_id`` / ``status``; transitions validated.
- :class:`TenantSetting` — per-tenant key/value override.  ``value``
  is JSONB (``Any`` in Python).  ``key`` is unique per tenant.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from qzdap_schema.ids import (
    PlanId,
    SubscriptionId,
    TenantId,
    TenantSettingId,
    UserId,
    WorkspaceId,
)

from qzdap.modules.platform.domain.value_objects import (
    PlanStatus,
    SubscriptionStatus,
)


def _utcnow() -> datetime:
    return datetime.now(UTC)


# ── Plan ──────────────────────────────────────────────────────────────────


@dataclass(slots=True, frozen=True)
class Plan:
    id: PlanId
    code: str
    display_name: str
    description: str
    limits: dict[str, Any]
    features: tuple[str, ...]
    price_monthly_usd: Decimal
    status: PlanStatus
    sort_order: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def create(
        cls,
        *,
        code: str,
        display_name: str,
        description: str = "",
        limits: dict[str, Any] | None = None,
        features: tuple[str, ...] | None = None,
        price_monthly_usd: Decimal = Decimal(0),
        status: PlanStatus = PlanStatus.ACTIVE,
        sort_order: int = 0,
        plan_id: PlanId | None = None,
        now: datetime | None = None,
    ) -> Plan:
        if not code or len(code) > 64:
            raise ValueError("Plan.code must be 1..64 chars")
        if not display_name or len(display_name) > 256:
            raise ValueError("Plan.display_name must be 1..256 chars")
        if price_monthly_usd < Decimal(0):
            raise ValueError("Plan.price_monthly_usd must be >= 0")
        ts = now or _utcnow()
        return cls(
            id=plan_id or PlanId(uuid4()),
            code=code,
            display_name=display_name,
            description=description,
            limits=dict(limits or {}),
            features=tuple(features or ()),
            price_monthly_usd=price_monthly_usd,
            status=status,
            sort_order=sort_order,
            created_at=ts,
            updated_at=ts,
        )


# ── Subscription ──────────────────────────────────────────────────────────


@dataclass(slots=True, frozen=True)
class Subscription:
    id: SubscriptionId
    tenant_id: TenantId
    plan_id: PlanId
    plan_code: str
    status: SubscriptionStatus
    started_at: datetime
    ends_at: datetime | None
    auto_renew: bool
    updated_by: UserId | None
    created_at: datetime
    updated_at: datetime
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def assign(
        cls,
        *,
        tenant_id: TenantId,
        plan_id: PlanId,
        plan_code: str,
        updated_by: UserId | None = None,
        started_at: datetime | None = None,
        ends_at: datetime | None = None,
        auto_renew: bool = True,
        metadata: dict[str, Any] | None = None,
        subscription_id: SubscriptionId | None = None,
        now: datetime | None = None,
    ) -> Subscription:
        ts = now or _utcnow()
        return cls(
            id=subscription_id or SubscriptionId(uuid4()),
            tenant_id=tenant_id,
            plan_id=plan_id,
            plan_code=plan_code,
            status=SubscriptionStatus.ACTIVE,
            started_at=started_at or ts,
            ends_at=ends_at,
            auto_renew=auto_renew,
            updated_by=updated_by,
            created_at=ts,
            updated_at=ts,
            metadata=dict(metadata or {}),
        )


# ── TenantSetting ────────────────────────────────────────────────────────


@dataclass(slots=True, frozen=True)
class TenantSetting:
    id: TenantSettingId
    tenant_id: TenantId
    workspace_id: WorkspaceId | None
    key: str
    value: Any
    updated_by: UserId | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def upsert(
        cls,
        *,
        tenant_id: TenantId,
        key: str,
        value: Any,
        workspace_id: WorkspaceId | None = None,
        updated_by: UserId | None = None,
        setting_id: TenantSettingId | None = None,
        now: datetime | None = None,
        created_at: datetime | None = None,
    ) -> TenantSetting:
        if not key or len(key) > 128:
            raise ValueError("TenantSetting.key must be 1..128 chars")
        ts = now or _utcnow()
        return cls(
            id=setting_id or TenantSettingId(uuid4()),
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            key=key,
            value=value,
            updated_by=updated_by,
            created_at=created_at or ts,
            updated_at=ts,
        )


__all__ = [
    "Plan",
    "Subscription",
    "TenantSetting",
]
