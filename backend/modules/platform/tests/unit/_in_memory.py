"""In-memory repositories + publisher for platform tests.

Mirror of the contract that the SQL adapter implements.  Each repo is
pure Python with no async dependencies, kept tiny so use-case tests
exercise the use-case, not the storage.
"""

from __future__ import annotations

from typing import Any

from qzdap_schema.ids import (
    PlanId,
    SubscriptionId,
    TenantId,
    TenantSettingId,
    WorkspaceId,
)

from qzdap.modules.platform.application.ports import (
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


class InMemoryPlanRepository(PlanRepository):
    def __init__(self) -> None:
        self._rows: dict[PlanId, Plan] = {}
        self._by_code: dict[str, PlanId] = {}

    async def get(self, *, plan_id: PlanId) -> Plan | None:
        return self._rows.get(plan_id)

    async def get_by_code(self, *, code: str) -> Plan | None:
        pid = self._by_code.get(code)
        if pid is None:
            return None
        return self._rows.get(pid)

    async def list(
        self, *, status: str | None = None, limit: int = 100, offset: int = 0
    ) -> list[Plan]:
        rows = sorted(
            self._rows.values(),
            key=lambda p: (p.sort_order, p.code),
        )
        if status is not None:
            rows = [p for p in rows if p.status.value == status]
        return rows[offset : offset + limit]

    async def add(self, plan: Plan) -> Plan:
        if plan.code in self._by_code:
            raise ValueError(f"plan code {plan.code!r} already exists")
        self._rows[plan.id] = plan
        self._by_code[plan.code] = plan.id
        return plan

    async def update(self, plan: Plan) -> Plan:
        # detach from previous code mapping if it changed (rare)
        prev = self._rows.get(plan.id)
        if prev is not None and prev.code != plan.code:
            self._by_code.pop(prev.code, None)
        self._rows[plan.id] = plan
        self._by_code[plan.code] = plan.id
        return plan


class InMemorySubscriptionRepository(SubscriptionRepository):
    def __init__(self) -> None:
        self._by_id: dict[SubscriptionId, Subscription] = {}
        self._by_tenant: dict[TenantId, SubscriptionId] = {}

    async def get(
        self, *, tenant_id: TenantId, subscription_id: SubscriptionId
    ) -> Subscription | None:
        row = self._by_id.get(subscription_id)
        if row is None or row.tenant_id != tenant_id:
            return None
        return row

    async def get_for_tenant(self, *, tenant_id: TenantId) -> Subscription | None:
        sid = self._by_tenant.get(tenant_id)
        if sid is None:
            return None
        return self._by_id.get(sid)

    async def add(self, subscription: Subscription) -> Subscription:
        if subscription.tenant_id in self._by_tenant:
            raise ValueError("tenant already has subscription")
        self._by_id[subscription.id] = subscription
        self._by_tenant[subscription.tenant_id] = subscription.id
        return subscription

    async def update(self, subscription: Subscription) -> Subscription:
        self._by_id[subscription.id] = subscription
        self._by_tenant[subscription.tenant_id] = subscription.id
        return subscription


class InMemoryTenantSettingRepository(TenantSettingRepository):
    def __init__(self) -> None:
        self._by_id: dict[TenantSettingId, TenantSetting] = {}
        self._by_tenant_key: dict[tuple[TenantId, str], TenantSettingId] = {}

    async def get(self, *, tenant_id: TenantId, key: str) -> TenantSetting | None:
        sid = self._by_tenant_key.get((tenant_id, key))
        if sid is None:
            return None
        return self._by_id.get(sid)

    async def list_for_tenant(self, *, tenant_id: TenantId) -> list[TenantSetting]:
        rows = [r for r in self._by_id.values() if r.tenant_id == tenant_id]
        return sorted(
            rows,
            key=lambda r: (
                r.workspace_id or WorkspaceId(int.from_bytes(b"\x00" * 16, "big")),
                r.key,
            ),
        )

    async def upsert(self, setting: TenantSetting) -> TenantSetting:
        prev_id = self._by_tenant_key.get((setting.tenant_id, setting.key))
        if prev_id is not None and prev_id != setting.id:
            self._by_id.pop(prev_id, None)
        self._by_id[setting.id] = setting
        self._by_tenant_key[(setting.tenant_id, setting.key)] = setting.id
        return setting


class RecordingPlatformEventPublisher(PlatformEventPublisher):
    def __init__(self) -> None:
        self.events: list[Any] = []

    async def publish(self, event: Any) -> None:
        self.events.append(event)

    def clear(self) -> None:
        self.events.clear()


__all__ = [
    "InMemoryPlanRepository",
    "InMemorySubscriptionRepository",
    "InMemoryTenantSettingRepository",
    "RecordingPlatformEventPublisher",
]
