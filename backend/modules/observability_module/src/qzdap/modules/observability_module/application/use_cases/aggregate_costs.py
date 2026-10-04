"""aggregate_costs — group / sum :class:`CostRecord`s.

Three ``group_by`` modes:

- ``cost_type`` → ``sum_by_cost_type`` (default)
- ``workspace`` → ``sum_by_workspace``
- ``model`` → ``sum_by_model``

All return a list of dict rows; the SQL adapter and the in-memory
adapter both produce the same shape so HTTP serialization is uniform.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from qzdap_kernel.errors import BusinessRuleError
from qzdap_schema.ids import TenantId, WorkspaceId

if TYPE_CHECKING:
    from qzdap.modules.observability_module.application.services import (
        ObservabilityService,
    )


_VALID_GROUP_BY = ("cost_type", "workspace", "model")


def build(service: ObservabilityService) -> Any:
    async def execute(
        *,
        tenant_id: TenantId,
        workspace_id: WorkspaceId | None = None,
        group_by: str = "cost_type",
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> list[dict[str, Any]]:
        if group_by not in _VALID_GROUP_BY:
            raise BusinessRuleError(
                message=f"group_by must be one of {_VALID_GROUP_BY}",
                code="GROUP_BY_INVALID",
            )
        if group_by == "cost_type":
            return await service.cost_repo.sum_by_cost_type(
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                since=since,
                until=until,
            )
        if group_by == "workspace":
            return await service.cost_repo.sum_by_workspace(
                tenant_id=tenant_id, since=since, until=until
            )
        return await service.cost_repo.sum_by_model(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            since=since,
            until=until,
        )

    return execute


__all__ = ["build"]
