"""Use-case tests for platform — exercises 7 use cases through service."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest

from qzdap.modules.platform.application.services import PlatformService
from qzdap.modules.platform.application.use_cases import (
    assign_subscription,
    get_plan,
    get_subscription,
    list_plans,
    list_settings,
    upsert_setting,
)
from qzdap.modules.platform.domain.errors import PlanNotFound
from qzdap.modules.platform.domain.value_objects import (
    PlanStatus,
    SubscriptionStatus,
)

from ._in_memory import (
    InMemoryPlanRepository,
    InMemorySubscriptionRepository,
    InMemoryTenantSettingRepository,
)


def _tenant_id():
    from qzdap_schema.ids import TenantId

    return TenantId(uuid4())


def _user_id():
    from qzdap_schema.ids import UserId

    return UserId(uuid4())


# ── list_plans ─────────────────────────────────────────────────────────────


class TestListPlans:
    async def test_empty_repo(self, service: PlatformService) -> None:
        execute = list_plans.build(service)
        assert await execute() == []

    async def test_with_seeded_plans(
        self, seeded_plan_repo: InMemoryPlanRepository
    ) -> None:
        svc = PlatformService.from_parts(
            plan_repo=seeded_plan_repo,
            subscription_repo=InMemorySubscriptionRepository(),
            setting_repo=InMemoryTenantSettingRepository(),
        )
        execute = list_plans.build(svc)
        rows = await execute()
        assert [p.code for p in rows] == ["free", "pro", "enterprise"]

    async def test_filter_by_status(
        self, seeded_plan_repo: InMemoryPlanRepository
    ) -> None:
        from dataclasses import replace

        plan = await seeded_plan_repo.get_by_code(code="pro")
        assert plan is not None
        await seeded_plan_repo.update(replace(plan, status=PlanStatus.RETIRED))
        svc = PlatformService.from_parts(
            plan_repo=seeded_plan_repo,
            subscription_repo=InMemorySubscriptionRepository(),
            setting_repo=InMemoryTenantSettingRepository(),
        )
        execute = list_plans.build(svc)
        active = await execute(status="active")
        assert {p.code for p in active} == {"free", "enterprise"}
        retired = await execute(status="retired")
        assert {p.code for p in retired} == {"pro"}

    async def test_limit_offset(self, seeded_plan_repo: InMemoryPlanRepository) -> None:
        svc = PlatformService.from_parts(
            plan_repo=seeded_plan_repo,
            subscription_repo=InMemorySubscriptionRepository(),
            setting_repo=InMemoryTenantSettingRepository(),
        )
        execute = list_plans.build(svc)
        first = await execute(limit=2, offset=0)
        second = await execute(limit=2, offset=2)
        assert [p.code for p in first] == ["free", "pro"]
        assert [p.code for p in second] == ["enterprise"]


# ── get_plan ──────────────────────────────────────────────────────────────


class TestGetPlan:
    async def test_get_by_code(
        self, service: PlatformService, seeded_plan_repo: InMemoryPlanRepository
    ) -> None:
        svc = PlatformService.from_parts(
            plan_repo=seeded_plan_repo,
            subscription_repo=service.subscription_repo,
            setting_repo=service.setting_repo,
        )
        execute = get_plan.build(svc)
        plan = await execute(code="pro")
        assert plan.code == "pro"
        assert plan.price_monthly_usd == Decimal("99.00")

    async def test_get_by_id(
        self, service: PlatformService, seeded_plan_repo: InMemoryPlanRepository
    ) -> None:
        plan = await seeded_plan_repo.get_by_code(code="free")
        assert plan is not None
        plan_id = str(plan.id)
        svc = PlatformService.from_parts(
            plan_repo=seeded_plan_repo,
            subscription_repo=service.subscription_repo,
            setting_repo=service.setting_repo,
        )
        execute = get_plan.build(svc)
        plan = await execute(plan_id=plan_id)
        assert plan.code == "free"

    async def test_missing_raises_not_found(self, service: PlatformService) -> None:
        execute = get_plan.build(service)
        with pytest.raises(PlanNotFound):
            await execute(code="does-not-exist")


# ── get_subscription ──────────────────────────────────────────────────────


class TestGetSubscription:
    async def test_returns_none_when_absent(self, service: PlatformService) -> None:
        execute = get_subscription.build(service)
        assert await execute(tenant_id=_tenant_id()) is None

    async def test_returns_existing(
        self, service: PlatformService, seeded_plan_repo: InMemoryPlanRepository
    ) -> None:
        svc = PlatformService.from_parts(
            plan_repo=seeded_plan_repo,
            subscription_repo=service.subscription_repo,
            setting_repo=service.setting_repo,
        )
        tenant = _tenant_id()
        user = _user_id()
        assign = assign_subscription.build(svc)
        await assign(tenant_id=tenant, plan_code="free", updated_by=user)
        execute = get_subscription.build(svc)
        sub = await execute(tenant_id=tenant)
        assert sub is not None
        assert sub.tenant_id == tenant
        assert sub.plan_code == "free"


# ── assign_subscription ────────────────────────────────────────────────────


class TestAssignSubscription:
    async def test_assign_to_known_plan(
        self, service: PlatformService, seeded_plan_repo: InMemoryPlanRepository
    ) -> None:
        svc = PlatformService.from_parts(
            plan_repo=seeded_plan_repo,
            subscription_repo=service.subscription_repo,
            setting_repo=service.setting_repo,
        )
        tenant = _tenant_id()
        execute = assign_subscription.build(svc)
        sub = await execute(tenant_id=tenant, plan_code="pro")
        assert sub.tenant_id == tenant
        assert sub.plan_code == "pro"
        assert sub.status is SubscriptionStatus.ACTIVE

    async def test_unknown_plan_raises(
        self, service: PlatformService, seeded_plan_repo: InMemoryPlanRepository
    ) -> None:
        svc = PlatformService.from_parts(
            plan_repo=seeded_plan_repo,
            subscription_repo=service.subscription_repo,
            setting_repo=service.setting_repo,
        )
        execute = assign_subscription.build(svc)
        with pytest.raises(PlanNotFound):
            await execute(tenant_id=_tenant_id(), plan_code="phantom")

    async def test_retired_plan_rejected(
        self, service: PlatformService, seeded_plan_repo: InMemoryPlanRepository
    ) -> None:
        from dataclasses import replace

        plan = await seeded_plan_repo.get_by_code(code="pro")
        assert plan is not None
        await seeded_plan_repo.update(replace(plan, status=PlanStatus.RETIRED))
        svc = PlatformService.from_parts(
            plan_repo=seeded_plan_repo,
            subscription_repo=service.subscription_repo,
            setting_repo=service.setting_repo,
        )
        execute = assign_subscription.build(svc)
        with pytest.raises(Exception) as excinfo:
            await execute(tenant_id=_tenant_id(), plan_code="pro")
        assert (
            "retired" in str(excinfo.value).lower()
            or getattr(excinfo.value, "code", "") == "PLAN_RETIRED"
        )

    async def test_reassign_switches_plan(
        self, service: PlatformService, seeded_plan_repo: InMemoryPlanRepository
    ) -> None:
        svc = PlatformService.from_parts(
            plan_repo=seeded_plan_repo,
            subscription_repo=service.subscription_repo,
            setting_repo=service.setting_repo,
        )
        tenant = _tenant_id()
        execute = assign_subscription.build(svc)
        await execute(tenant_id=tenant, plan_code="free")
        updated = await execute(tenant_id=tenant, plan_code="enterprise")
        assert updated.plan_code == "enterprise"
        sub = await service.subscription_repo.get_for_tenant(tenant_id=tenant)
        assert sub is not None
        assert sub.plan_code == "enterprise"


# ── list_settings ──────────────────────────────────────────────────────────


class TestListSettings:
    async def test_empty(self, service: PlatformService) -> None:
        execute = list_settings.build(service)
        assert await execute(tenant_id=_tenant_id()) == []

    async def test_returns_only_tenant_scenarios(
        self, service: PlatformService, tenant_id, other_tenant_id
    ) -> None:
        upsert = upsert_setting.build(service)
        await upsert(tenant_id=tenant_id, key="rate", value=10)
        await upsert(tenant_id=tenant_id, key="model", value="gpt-4o")
        await upsert(tenant_id=other_tenant_id, key="rate", value=99)
        execute = list_settings.build(service)
        rows = await execute(tenant_id=tenant_id)
        assert {s.key for s in rows} == {"rate", "model"}
        assert all(s.tenant_id == tenant_id for s in rows)


# ── upsert_setting ─────────────────────────────────────────────────────────


class TestUpsertSetting:
    async def test_creates_when_absent(self, service: PlatformService) -> None:
        execute = upsert_setting.build(service)
        setting = await execute(
            tenant_id=_tenant_id(),
            key="default_model",
            value="gpt-4o-mini",
        )
        assert setting.key == "default_model"
        assert setting.value == "gpt-4o-mini"

    async def test_updates_when_present(self, service: PlatformService) -> None:
        tenant = _tenant_id()
        execute = upsert_setting.build(service)
        await execute(tenant_id=tenant, key="model", value="gpt-4o")
        await execute(tenant_id=tenant, key="model", value="gpt-4o-mini")
        execute_list = list_settings.build(service)
        rows = await execute_list(tenant_id=tenant)
        assert len(rows) == 1
        assert rows[0].value == "gpt-4o-mini"

    async def test_complex_value_round_trip(self, service: PlatformService) -> None:
        execute = upsert_setting.build(service)
        value = {"limits": {"max_turns": 1000}, "tiers": ["a", "b"]}
        setting = await execute(tenant_id=_tenant_id(), key="cfg", value=value)
        assert setting.value == value


# ── aggregate_costs (placeholder parity) ──────────────────────────────────


class TestAggregateCosts:
    async def test_returns_empty(self, service: PlatformService) -> None:
        from qzdap.modules.platform.application.use_cases import (
            aggregate_costs,
        )

        execute = aggregate_costs.build(service)
        result = await execute(tenant_id=_tenant_id(), group_by="cost_type")
        assert result == []


# ── cross-tenant isolation ────────────────────────────────────────────────


class TestCrossTenantIsolation:
    async def test_setting_tenant_a_does_not_appear_for_tenant_b(
        self, service: PlatformService
    ) -> None:
        tenant_a = _tenant_id()
        tenant_b = _tenant_id()
        upsert = upsert_setting.build(service)
        await upsert(tenant_id=tenant_a, key="x", value=1)
        list_a = list_settings.build(service)
        list_b = list_settings.build(service)
        assert await list_a(tenant_id=tenant_a) != []
        assert await list_b(tenant_id=tenant_b) == []

    async def test_subscription_per_tenant_unique(
        self, service: PlatformService, seeded_plan_repo: InMemoryPlanRepository
    ) -> None:
        svc = PlatformService.from_parts(
            plan_repo=seeded_plan_repo,
            subscription_repo=service.subscription_repo,
            setting_repo=service.setting_repo,
        )
        tenant_a = _tenant_id()
        tenant_b = _tenant_id()
        assign = assign_subscription.build(svc)
        await assign(tenant_id=tenant_a, plan_code="free")
        await assign(tenant_id=tenant_b, plan_code="enterprise")
        get_sub = get_subscription.build(svc)
        sub_a = await get_sub(tenant_id=tenant_a)
        sub_b = await get_sub(tenant_id=tenant_b)
        assert sub_a is not None and sub_b is not None
        assert sub_a.tenant_id == tenant_a
        assert sub_b.tenant_id == tenant_b
        assert sub_a.id != sub_b.id
        assert sub_a.plan_code == "free"
        assert sub_b.plan_code == "enterprise"


# ── repo port compliance ──────────────────────────────────────────────────


class TestPortCompliance:
    def test_in_memory_repos_satisfy_protocols(self) -> None:
        from qzdap.modules.platform.application.ports import (
            PlanRepository,
            SubscriptionRepository,
            TenantSettingRepository,
        )

        assert isinstance(InMemoryPlanRepository(), PlanRepository)
        assert isinstance(InMemorySubscriptionRepository(), SubscriptionRepository)
        assert isinstance(InMemoryTenantSettingRepository(), TenantSettingRepository)
