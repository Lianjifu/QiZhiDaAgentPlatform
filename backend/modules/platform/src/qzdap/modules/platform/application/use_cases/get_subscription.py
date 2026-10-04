"""get_subscription — fetch a tenant's current subscription."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from qzdap_schema.ids import TenantId

from qzdap.modules.platform.domain.entities import Subscription

if TYPE_CHECKING:
    from qzdap.modules.platform.application.services import PlatformService


def build(service: PlatformService) -> Any:
    async def execute(*, tenant_id: TenantId) -> Subscription | None:
        return await service.subscription_repo.get_for_tenant(tenant_id=tenant_id)

    return execute


__all__ = ["build"]
