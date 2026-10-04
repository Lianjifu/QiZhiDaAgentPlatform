"""list_costs — paginated retrieval of :class:`CostRecord`s."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from qzdap_schema.ids import TenantId, WorkspaceId

from qzdap.modules.observability_module.domain.entities import CostRecord
from qzdap.modules.observability_module.domain.value_objects import CostType

if TYPE_CHECKING:
    from qzdap.modules.observability_module.application.services import (
        ObservabilityService,
    )


def build(service: ObservabilityService) -> Any:
    async def execute(
        *,
        tenant_id: TenantId,
        workspace_id: WorkspaceId | None,
        cost_type: CostType | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[CostRecord]:
        return await service.cost_repo.list_records(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            cost_type=cost_type,
            since=since,
            until=until,
            limit=limit,
            offset=offset,
        )

    return execute


__all__ = ["build"]
