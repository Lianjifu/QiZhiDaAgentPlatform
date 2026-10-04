"""list_settings — list all settings for a tenant."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from qzdap_schema.ids import TenantId

from qzdap.modules.platform.domain.entities import TenantSetting

if TYPE_CHECKING:
    from qzdap.modules.platform.application.services import PlatformService


def build(service: PlatformService) -> Any:
    async def execute(*, tenant_id: TenantId) -> list[TenantSetting]:
        return await service.setting_repo.list_for_tenant(tenant_id=tenant_id)

    return execute


__all__ = ["build"]
