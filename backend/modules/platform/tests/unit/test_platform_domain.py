"""Domain-layer tests for Plan / Subscription / TenantSetting."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from qzdap.modules.platform.domain.entities import (
    Plan,
    Subscription,
    TenantSetting,
)
from qzdap.modules.platform.domain.errors import PlanNotFound
from qzdap.modules.platform.domain.value_objects import (
    PlanStatus,
    SubscriptionStatus,
)


def _tenant_id():
    from qzdap_schema.ids import TenantId

    return TenantId(uuid4())


def _plan_id():
    from qzdap_schema.ids import PlanId

    return PlanId(uuid4())


def _user_id():
    from qzdap_schema.ids import UserId

    return UserId(uuid4())


def _workspace_id():
    from qzdap_schema.ids import WorkspaceId

    return WorkspaceId(uuid4())


# ── Plan ───────────────────────────────────────────────────────────────────


class TestPlan:
    def test_create_minimal(self) -> None:
        plan = Plan.create(code="free", display_name="Free")
        assert plan.code == "free"
        assert plan.display_name == "Free"
        assert plan.limits == {}
        assert plan.features == ()
        assert plan.price_monthly_usd == Decimal(0)
        assert plan.status is PlanStatus.ACTIVE
        assert plan.sort_order == 0
        assert isinstance(plan.created_at, datetime)
        assert plan.created_at == plan.updated_at

    def test_create_full(self) -> None:
        now = datetime.now(UTC)
        plan = Plan.create(
            code="pro",
            display_name="Pro",
            description="Small teams",
            limits={"max_turns": 5_000, "max_workspaces": 10},
            features=("eval gate", "private registry"),
            price_monthly_usd=Decimal("99.00"),
            status=PlanStatus.ACTIVE,
            sort_order=20,
            now=now,
        )
        assert plan.description == "Small teams"
        assert plan.limits == {"max_turns": 5_000, "max_workspaces": 10}
        assert plan.features == ("eval gate", "private registry")
        assert plan.price_monthly_usd == Decimal("99.00")
        assert plan.created_at == now

    def test_code_too_long_rejected(self) -> None:
        with pytest.raises(ValueError, match="1..64"):
            Plan.create(code="x" * 65, display_name="X")

    def test_empty_code_rejected(self) -> None:
        with pytest.raises(ValueError, match="1..64"):
            Plan.create(code="", display_name="X")

    def test_display_name_too_long_rejected(self) -> None:
        with pytest.raises(ValueError, match="1..256"):
            Plan.create(code="ok", display_name="x" * 257)

    def test_negative_price_rejected(self) -> None:
        with pytest.raises(ValueError, match=">= 0"):
            Plan.create(code="bad", display_name="Bad", price_monthly_usd=Decimal(-1))

    def test_is_frozen(self) -> None:
        plan = Plan.create(code="free", display_name="Free")
        with pytest.raises((AttributeError, Exception)):
            plan.code = "modified"  # type: ignore[misc]


# ── Subscription ───────────────────────────────────────────────────────────


class TestSubscription:
    def test_assign_defaults(self) -> None:
        tenant = _tenant_id()
        plan = _plan_id()
        sub = Subscription.assign(tenant_id=tenant, plan_id=plan, plan_code="free")
        assert sub.tenant_id == tenant
        assert sub.plan_id == plan
        assert sub.plan_code == "free"
        assert sub.status is SubscriptionStatus.ACTIVE
        assert sub.auto_renew is True
        assert sub.ends_at is None
        assert sub.updated_by is None
        assert sub.metadata == {}

    def test_assign_full(self) -> None:
        tenant = _tenant_id()
        plan = _plan_id()
        user = _user_id()
        now = datetime.now(UTC)
        sub = Subscription.assign(
            tenant_id=tenant,
            plan_id=plan,
            plan_code="pro",
            updated_by=user,
            auto_renew=False,
            ends_at=now,
            metadata={"source": "sales"},
        )
        assert sub.updated_by == user
        assert sub.auto_renew is False
        assert sub.ends_at == now
        assert sub.metadata == {"source": "sales"}

    def test_is_frozen(self) -> None:
        sub = Subscription.assign(
            tenant_id=_tenant_id(), plan_id=_plan_id(), plan_code="free"
        )
        with pytest.raises((AttributeError, Exception)):
            sub.status = SubscriptionStatus.CANCELLED  # type: ignore[misc]


# ── TenantSetting ─────────────────────────────────────────────────────────


class TestTenantSetting:
    def test_upsert_creates(self) -> None:
        tenant = _tenant_id()
        setting = TenantSetting.upsert(tenant_id=tenant, key="rate_limit", value=42)
        assert setting.tenant_id == tenant
        assert setting.key == "rate_limit"
        assert setting.value == 42
        assert setting.updated_by is None
        assert setting.workspace_id is None

    def test_upsert_with_workspace(self) -> None:
        tenant = _tenant_id()
        ws = _workspace_id()
        setting = TenantSetting.upsert(
            tenant_id=tenant, workspace_id=ws, key="model", value="gpt-4o"
        )
        assert setting.workspace_id == ws
        assert setting.value == "gpt-4o"

    def test_upsert_preserves_created_at(self) -> None:
        tenant = _tenant_id()
        created = datetime.now(UTC)
        setting = TenantSetting.upsert(
            tenant_id=tenant,
            key="x",
            value=1,
            created_at=created,
        )
        assert setting.created_at == created
        assert setting.updated_at >= created

    def test_empty_key_rejected(self) -> None:
        with pytest.raises(ValueError, match="1..128"):
            TenantSetting.upsert(tenant_id=_tenant_id(), key="", value=1)

    def test_key_too_long_rejected(self) -> None:
        with pytest.raises(ValueError, match="1..128"):
            TenantSetting.upsert(tenant_id=_tenant_id(), key="k" * 129, value=1)

    def test_is_frozen(self) -> None:
        setting = TenantSetting.upsert(tenant_id=_tenant_id(), key="x", value=1)
        with pytest.raises((AttributeError, Exception)):
            setting.value = 99  # type: ignore[misc]


# ── Error hierarchy ───────────────────────────────────────────────────────


class TestErrors:
    def test_plan_not_found_is_not_found_error(self) -> None:
        err = PlanNotFound("missing")
        from qzdap_kernel.errors import NotFoundError

        assert isinstance(err, NotFoundError)
        assert err.code == "PLAN_NOT_FOUND"

    def test_all_have_codes(self) -> None:
        from qzdap.modules.platform.domain.errors import (
            PlanAlreadyExists,
            SubscriptionInvalidTransition,
            TenantSettingConflict,
            TenantSettingNotFound,
        )

        assert PlanAlreadyExists("x").code == "PLAN_ALREADY_EXISTS"
        assert (
            SubscriptionInvalidTransition("x").code == "SUBSCRIPTION_INVALID_TRANSITION"
        )
        assert TenantSettingNotFound("x").code == "TENANT_SETTING_NOT_FOUND"
        assert TenantSettingConflict("x").code == "TENANT_SETTING_CONFLICT"


# ── Default plans fixture ────────────────────────────────────────────────


class TestDefaultPlansFixture:
    def test_three_default_specs(self) -> None:
        from qzdap.modules.platform.fixtures.default_plans import DEFAULT_PLANS

        assert len(DEFAULT_PLANS) == 3
        codes = {s.code for s in DEFAULT_PLANS}
        assert codes == {"free", "pro", "enterprise"}

    def test_build_default_plan(self) -> None:
        from qzdap.modules.platform.fixtures.default_plans import (
            DEFAULT_PLANS,
            build_default_plan,
        )

        for spec in DEFAULT_PLANS:
            plan = build_default_plan(spec)
            assert plan.code == spec.code
            assert plan.display_name == spec.display_name
            assert plan.status is PlanStatus.ACTIVE
            assert plan.price_monthly_usd == spec.price_monthly_usd
            assert plan.features == spec.features
