"""Async-SQLAlchemy implementation of the platform ports.

- :class:`SqlPlanRepository` — global ``plans`` table (no tenant scope)
- :class:`SqlSubscriptionRepository` — ``subscriptions`` table, UQ
  ``tenant_id`` enforces one sub per tenant
- :class:`SqlTenantSettingRepository` — ``tenant_settings`` table, UQ
  ``(tenant_id, key)`` enforces idempotent upsert
- :class:`ObservabilityCostRepositoryBridge` — implements the
  platform ``CostRecordRepository`` port by forwarding to the
  observability module's :class:`SqlCostRecordRepository`. This
  keeps the cross-module dependency at the adapter edge (no
  observability → platform import inversion).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from qzdap_schema.ids import (
    PlanId,
    SubscriptionId,
    TenantId,
    WorkspaceId,
)
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from qzdap.modules.platform.adapter.persistence.mappers import (
    plan_to_domain,
    plan_to_orm,
    subscription_to_domain,
    subscription_to_orm,
    tenant_setting_to_domain,
    tenant_setting_to_orm,
)
from qzdap.modules.platform.adapter.persistence.models import (
    PlanORM,
    SubscriptionORM,
    TenantSettingORM,
)
from qzdap.modules.platform.application.ports import (
    PlanRepository,
    SubscriptionRepository,
    TenantSettingRepository,
)
from qzdap.modules.platform.domain.entities import (
    Plan,
    Subscription,
    TenantSetting,
)
from qzdap.modules.platform.domain.errors import PlanAlreadyExists

# ── PlanRepository ────────────────────────────────────────────────────────


class SqlPlanRepository(PlanRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, *, plan_id: PlanId) -> Plan | None:
        row = (
            await self._session.execute(select(PlanORM).where(PlanORM.id == plan_id))
        ).scalar_one_or_none()
        return plan_to_domain(row) if row is not None else None

    async def get_by_code(self, *, code: str) -> Plan | None:
        row = (
            await self._session.execute(select(PlanORM).where(PlanORM.code == code))
        ).scalar_one_or_none()
        return plan_to_domain(row) if row is not None else None

    async def list(
        self, *, status: str | None = None, limit: int = 100, offset: int = 0
    ) -> list[Plan]:
        if limit <= 0:
            raise ValueError("limit must be > 0")
        stmt = (
            select(PlanORM)
            .order_by(PlanORM.sort_order.asc(), PlanORM.code.asc())
            .limit(limit)
            .offset(max(0, offset))
        )
        if status is not None:
            stmt = stmt.where(PlanORM.status == status)
        rows = (await self._session.execute(stmt)).scalars().all()
        return [plan_to_domain(r) for r in rows]

    async def add(self, plan: Plan) -> Plan:
        try:
            self._session.add(plan_to_orm(plan))
            await self._session.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            raise PlanAlreadyExists(f"plan code {plan.code!r} already exists") from exc
        return plan

    async def update(self, plan: Plan) -> Plan:
        row = (
            await self._session.execute(select(PlanORM).where(PlanORM.id == plan.id))
        ).scalar_one()
        row.code = plan.code
        row.display_name = plan.display_name
        row.description = plan.description
        row.limits = dict(plan.limits)
        row.features = list(plan.features)
        row.price_monthly_usd = plan.price_monthly_usd
        row.status = plan.status.value
        row.sort_order = plan.sort_order
        await self._session.flush()
        return plan_to_domain(row)


# ── SubscriptionRepository ────────────────────────────────────────────────


class SqlSubscriptionRepository(SubscriptionRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(
        self, *, tenant_id: TenantId, subscription_id: SubscriptionId
    ) -> Subscription | None:
        row = (
            await self._session.execute(
                select(SubscriptionORM).where(
                    SubscriptionORM.tenant_id == tenant_id,
                    SubscriptionORM.id == subscription_id,
                )
            )
        ).scalar_one_or_none()
        return subscription_to_domain(row) if row is not None else None

    async def get_for_tenant(self, *, tenant_id: TenantId) -> Subscription | None:
        row = (
            await self._session.execute(
                select(SubscriptionORM).where(SubscriptionORM.tenant_id == tenant_id)
            )
        ).scalar_one_or_none()
        return subscription_to_domain(row) if row is not None else None

    async def add(self, subscription: Subscription) -> Subscription:
        try:
            self._session.add(subscription_to_orm(subscription))
            await self._session.flush()
        except IntegrityError:
            await self._session.rollback()
            raise
        return subscription

    async def update(self, subscription: Subscription) -> Subscription:
        row = (
            await self._session.execute(
                select(SubscriptionORM).where(SubscriptionORM.id == subscription.id)
            )
        ).scalar_one()
        row.plan_id = subscription.plan_id
        row.plan_code = subscription.plan_code
        row.status = subscription.status.value
        row.started_at = subscription.started_at
        row.ends_at = subscription.ends_at
        row.auto_renew = subscription.auto_renew
        row.updated_by = subscription.updated_by
        row.metadata_ = dict(subscription.metadata)
        await self._session.flush()
        return subscription_to_domain(row)


# ── TenantSettingRepository ───────────────────────────────────────────────


class SqlTenantSettingRepository(TenantSettingRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, *, tenant_id: TenantId, key: str) -> TenantSetting | None:
        row = (
            await self._session.execute(
                select(TenantSettingORM).where(
                    TenantSettingORM.tenant_id == tenant_id,
                    TenantSettingORM.key == key,
                )
            )
        ).scalar_one_or_none()
        return tenant_setting_to_domain(row) if row is not None else None

    async def list_for_tenant(self, *, tenant_id: TenantId) -> list[TenantSetting]:
        rows = (
            (
                await self._session.execute(
                    select(TenantSettingORM)
                    .where(TenantSettingORM.tenant_id == tenant_id)
                    .order_by(
                        TenantSettingORM.workspace_id.asc().nulls_first(),
                        TenantSettingORM.key.asc(),
                    )
                )
            )
            .scalars()
            .all()
        )
        return [tenant_setting_to_domain(r) for r in rows]

    async def upsert(self, setting: TenantSetting) -> TenantSetting:
        existing = (
            await self._session.execute(
                select(TenantSettingORM).where(
                    TenantSettingORM.tenant_id == setting.tenant_id,
                    TenantSettingORM.key == setting.key,
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            self._session.add(tenant_setting_to_orm(setting))
            await self._session.flush()
            return setting
        existing.workspace_id = setting.workspace_id
        existing.value = setting.value
        existing.updated_by = setting.updated_by
        existing.updated_at = setting.updated_at
        await self._session.flush()
        return tenant_setting_to_domain(existing)


# ── Cost bridge ─────────────────────────────────────────────────────────


class ObservabilityCostRepositoryBridge:
    """Forwards to ``observability_module.SqlCostRecordRepository``.

    Platform depends only on its own :class:`CostRecordRepository`
    Protocol — the composition root wires this bridge so platform can
    roll up tenant spend without importing the observability module
    at the application layer.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._inner: Any = None

    def _get_inner(self) -> Any:
        if self._inner is None:
            # Imported lazily so platform boots even when observability
            # is absent (e.g. lightweight test profiles).
            from qzdap.modules.observability_module.adapter.persistence.repositories import (
                SqlCostRecordRepository,
            )

            self._inner = SqlCostRecordRepository(self._session)
        return self._inner

    async def sum_by_cost_type(
        self,
        *,
        tenant_id: TenantId,
        workspace_id: WorkspaceId | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> list[dict[str, Any]]:
        return await self._get_inner().sum_by_cost_type(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            since=since,
            until=until,
        )

    async def sum_by_workspace(
        self,
        *,
        tenant_id: TenantId,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> list[dict[str, Any]]:
        return await self._get_inner().sum_by_workspace(
            tenant_id=tenant_id,
            since=since,
            until=until,
        )


__all__ = [
    "ObservabilityCostRepositoryBridge",
    "SqlPlanRepository",
    "SqlSubscriptionRepository",
    "SqlTenantSettingRepository",
]
