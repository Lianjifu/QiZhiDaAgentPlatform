"""record_cost — create a single :class:`CostRecord`.

Like record_run, used by the HTTP layer's manual ingest path (rarely).
The subscriber path creates CostRecords automatically.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from qzdap_kernel.errors import BusinessRuleError

from qzdap.modules.observability_module.domain.entities import CostRecord
from qzdap.modules.observability_module.domain.value_objects import CostType

if TYPE_CHECKING:
    from qzdap.modules.observability_module.application.services import (
        ObservabilityService,
    )


def build(service: ObservabilityService) -> Any:
    async def execute(cmd: dict[str, Any]) -> CostRecord:
        try:
            cost_type = CostType(cmd["cost_type"])
        except (KeyError, ValueError) as exc:
            raise BusinessRuleError(
                message=f"invalid cost_type: {exc}",
                code="COST_TYPE_INVALID",
            ) from exc
        try:
            record = CostRecord.create(
                tenant_id=cmd["tenant_id"],
                workspace_id=cmd["workspace_id"],
                run_id=cmd["run_id"],
                cost_type=cost_type,
                amount_usd=cmd["amount_usd"],
                quantity=cmd.get("quantity"),
                unit=cmd.get("unit", "call"),
                currency=cmd.get("currency", service.pricing.currency),
                model_id=cmd.get("model_id"),
                metadata=cmd.get("metadata"),
            )
        except ValueError as exc:
            raise BusinessRuleError(message=str(exc), code="COST_INVALID") from exc
        return await service.cost_repo.add(record)

    return execute


__all__ = ["build"]
