"""**订阅的落库映射** ✓（P-13 的 mypy 扫出来的真缺陷 ✓）。

⚠️ **之前写订阅必炸** ✓ —— `Subscription` 领域实体**没有** `workspace_id` ✓，
ORM 却映射了它 ✓ → `subscription_to_orm` 读一个不存在的属性 ✓ →
`AttributeError` ✓（表里一行数据都没有 ✓ → 一直没人走过 ✓）。

验收 ✓：**映射器不再碰那个不存在的属性** ✓（订阅是租户级的 ✓ —— 唯一约束就在
`tenant_id` 上 ✓ → 迁移 0060 把那列删了 ✓）。
"""

from __future__ import annotations

from uuid import uuid4

from qzdap.modules.platform.adapter.persistence.mappers import subscription_to_orm
from qzdap.modules.platform.domain.entities import Subscription
from qzdap_kernel.ids import PlanId, TenantId


def _subscription() -> Subscription:
    return Subscription.assign(
        tenant_id=TenantId(uuid4()),
        plan_id=PlanId(uuid4()),
        plan_code="free",
    )


def test_the_subscription_maps_without_a_workspace() -> None:
    """**映射得出来** ✓（之前必然 `AttributeError` ✓）。"""
    sub = _subscription()

    row = subscription_to_orm(sub)

    assert row.tenant_id == sub.tenant_id
    assert row.plan_id == sub.plan_id
    assert row.plan_code == "free"
    # ⚠️ **ORM 上没有 workspace_id 了** ✓（订阅是租户级的 ✓ —— 迁移 0060 ✓）。
    assert not hasattr(row, "workspace_id")


def test_the_domain_entity_has_no_workspace_field() -> None:
    """**领域实体本来就没有工作区** ✓（租户级 ✓）。"""
    sub = _subscription()

    assert not hasattr(sub, "workspace_id")
