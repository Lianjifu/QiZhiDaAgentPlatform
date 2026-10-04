"""aggregate_costs — tenant spend roll-up backed by observability.

Platform reads aggregated cost data through its
:class:`CostRecordRepository` port. The bridge forwards to the
observability module's SQL repository so platform never depends on
observability's adapter internals — it only knows the protocol.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from qzdap.modules.platform.application.services import PlatformService


def build(service: PlatformService) -> Any:
    async def aggregate(
        *,
        tenant_id: object,
        group_by: str = "cost_type",
        since: datetime | None = None,
        until: datetime | None = None,
        workspace_id: object | None = None,
    ) -> list[dict[str, object]]:
        repo = service.cost_repo
        if repo is None:
            # Cost source not wired (observability disabled in this
            # deployment). Return an empty result so the HTTP handler
            # still answers 200; the operator can see the gap in
            # monitoring instead of receiving a 503.
            return []
        if group_by == "workspace":
            rows = await repo.sum_by_workspace(
                tenant_id=tenant_id,
                since=since,
                until=until,
            )
        else:
            # default — cost_type
            rows = await repo.sum_by_cost_type(
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                since=since,
                until=until,
            )
        return [dict(row) for row in rows]

    return aggregate


__all__ = ["build"]