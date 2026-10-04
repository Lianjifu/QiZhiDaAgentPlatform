"""Platform application services.

Mirrors the :class:`ObservabilityService` shape: a dataclass with
injected ports and a ``_use_cases`` dict built in ``__post_init__``
so HTTP / CLI callers reach the use cases via attribute access
(e.g. ``svc.list_plans``).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from qzdap.modules.platform.application.ports import (
    CostRecordRepository,
    PlanRepository,
    PlatformEventPublisher,
    SubscriptionRepository,
    TenantSettingRepository,
)
from qzdap.modules.platform.domain.entities import (
    Plan,
    Subscription,
    TenantSetting,
)


@dataclass(slots=True)
class PlatformService:
    plan_repo: PlanRepository
    subscription_repo: SubscriptionRepository
    setting_repo: TenantSettingRepository
    publisher: PlatformEventPublisher | None = None
    # Optional — set by the composition root when observability is
    # wired. ``aggregate_costs`` falls back to an empty list when
    # missing (keeps the platform HTTP surface alive even in tests
    # that don't boot observability).
    cost_repo: CostRecordRepository | None = None
    _use_cases: dict[str, Callable[..., Awaitable[Any]]] = field(
        default_factory=dict, repr=False
    )

    @classmethod
    def from_parts(
        cls,
        *,
        plan_repo: PlanRepository,
        subscription_repo: SubscriptionRepository,
        setting_repo: TenantSettingRepository,
        publisher: PlatformEventPublisher | None = None,
        cost_repo: CostRecordRepository | None = None,
    ) -> PlatformService:
        return cls(
            plan_repo=plan_repo,
            subscription_repo=subscription_repo,
            setting_repo=setting_repo,
            publisher=publisher,
            cost_repo=cost_repo,
        )

    def __post_init__(self) -> None:
        from qzdap.modules.platform.application.use_cases import (
            assign_subscription,
            get_plan,
            get_subscription,
            list_plans,
            list_settings,
            upsert_setting,
        )

        self._use_cases = {
            "list_plans": list_plans.build(self),
            "get_plan": get_plan.build(self),
            "get_my_subscription": get_subscription.build(self),
            "assign_subscription": assign_subscription.build(self),
            "list_settings": list_settings.build(self),
            "upsert_tenant_setting": upsert_setting.build(self),
        }

    # ── use case attribute access ────────────────────────────────────────

    async def list_plans(
        self,
        *,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Plan]:
        return await self._use_cases["list_plans"](
            status=status, limit=limit, offset=offset
        )

    async def get_plan(
        self, *, plan_id: str | None = None, code: str | None = None
    ) -> Plan:
        return await self._use_cases["get_plan"](plan_id=plan_id, code=code)

    async def get_my_subscription(self, *, tenant_id: object) -> Subscription | None:
        return await self._use_cases["get_my_subscription"](tenant_id=tenant_id)

    async def assign_subscription(
        self,
        *,
        tenant_id: object,
        plan_code: str,
        updated_by: object | None = None,
        auto_renew: bool = True,
    ) -> Subscription:
        return await self._use_cases["assign_subscription"](
            tenant_id=tenant_id,
            plan_code=plan_code,
            updated_by=updated_by,
            auto_renew=auto_renew,
        )

    async def list_settings(self, *, tenant_id: object) -> list[TenantSetting]:
        return await self._use_cases["list_settings"](tenant_id=tenant_id)

    async def upsert_tenant_setting(
        self,
        *,
        tenant_id: object,
        key: str,
        value: object,
        updated_by: object | None = None,
    ) -> TenantSetting:
        return await self._use_cases["upsert_tenant_setting"](
            tenant_id=tenant_id,
            key=key,
            value=value,
            updated_by=updated_by,
        )


__all__ = ["PlatformService"]
