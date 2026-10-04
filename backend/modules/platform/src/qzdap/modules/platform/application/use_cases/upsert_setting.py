"""upsert_setting — create-or-replace a tenant setting by key."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from qzdap_schema.ids import TenantId, UserId

from qzdap.modules.platform.domain.entities import TenantSetting

if TYPE_CHECKING:
    from qzdap.modules.platform.application.services import PlatformService


def build(service: PlatformService) -> Any:
    async def execute(
        *,
        tenant_id: TenantId,
        key: str,
        value: object,
        updated_by: UserId | None = None,
    ) -> TenantSetting:
        now = datetime.now(UTC)
        existing = await service.setting_repo.get(tenant_id=tenant_id, key=key)
        if existing is None:
            setting = TenantSetting.upsert(
                tenant_id=tenant_id,
                key=key,
                value=value,
                updated_by=updated_by,
                now=now,
            )
        else:
            setting = TenantSetting.upsert(
                tenant_id=existing.tenant_id,
                workspace_id=existing.workspace_id,
                key=existing.key,
                value=value,
                updated_by=updated_by,
                setting_id=existing.id,
                created_at=existing.created_at,
                now=now,
            )
        return await service.setting_repo.upsert(setting)

    return execute


__all__ = ["build"]
