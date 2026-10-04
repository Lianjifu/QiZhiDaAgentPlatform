"""Platform application ports (Protocols)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from qzdap_schema.ids import (
    PlanId,
    SubscriptionId,
    TenantId,
    WorkspaceId,
)

from qzdap.modules.platform.domain.entities import (
    Plan,
    Subscription,
    TenantSetting,
)


@runtime_checkable
class PlanRepository(Protocol):
    async def get(self, *, plan_id: PlanId) -> Plan | None: ...
    async def get_by_code(self, *, code: str) -> Plan | None: ...
    async def list(
        self, *, status: str | None = None, limit: int = 100, offset: int = 0
    ) -> list[Plan]: ...
    async def add(self, plan: Plan) -> Plan: ...
    async def update(self, plan: Plan) -> Plan: ...


@runtime_checkable
class SubscriptionRepository(Protocol):
    async def get(
        self, *, tenant_id: TenantId, subscription_id: SubscriptionId
    ) -> Subscription | None: ...
    async def get_for_tenant(self, *, tenant_id: TenantId) -> Subscription | None: ...
    async def add(self, subscription: Subscription) -> Subscription: ...
    async def update(self, subscription: Subscription) -> Subscription: ...


@runtime_checkable
class TenantSettingRepository(Protocol):
    async def get(self, *, tenant_id: TenantId, key: str) -> TenantSetting | None: ...
    async def list_for_tenant(self, *, tenant_id: TenantId) -> list[TenantSetting]: ...
    async def upsert(self, setting: TenantSetting) -> TenantSetting: ...


@runtime_checkable
class PlatformEventPublisher(Protocol):
    async def publish(self, event: object) -> None: ...


@runtime_checkable
class CostRecordRepository(Protocol):
    """Cross-module port — backed by the observability module's
    ``CostRecordRepository`` so platform can roll up tenant spend
    without importing observability's adapter layer.

    Concrete impl lives in ``adapter/persistence/cost_repo_bridge.py``
    — it forwards to a SQL-backed observability session.
    """

    async def sum_by_cost_type(
        self,
        *,
        tenant_id: TenantId,
        workspace_id: WorkspaceId | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> list[dict[str, Any]]: ...

    async def sum_by_workspace(
        self,
        *,
        tenant_id: TenantId,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> list[dict[str, Any]]: ...


__all__ = [
    "CostRecordRepository",
    "PlanRepository",
    "PlatformEventPublisher",
    "SubscriptionRepository",
    "TenantSettingRepository",
]
