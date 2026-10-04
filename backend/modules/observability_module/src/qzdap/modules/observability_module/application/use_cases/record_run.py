"""record_run — create a single :class:`RunRecord` from caller-provided fields.

Used by the HTTP layer's /v1/observability/runs manual ingest path
(some businesses want to record custom runs that don't come from the
event bus).  The subscriber path goes via :class:`ObservabilityRecorder`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from qzdap_kernel.errors import BusinessRuleError

from qzdap.modules.observability_module.domain.entities import RunRecord
from qzdap.modules.observability_module.domain.value_objects import (
    RunStatus,
    RunType,
)

if TYPE_CHECKING:
    from qzdap.modules.observability_module.application.services import (
        ObservabilityService,
    )


def build(service: ObservabilityService) -> Any:
    async def execute(cmd: dict[str, Any]) -> RunRecord:
        try:
            run_type = RunType(cmd["run_type"])
        except (KeyError, ValueError) as exc:
            raise BusinessRuleError(
                message=f"invalid run_type: {exc}", code="RUN_TYPE_INVALID"
            ) from exc
        try:
            status = RunStatus(cmd.get("status", "succeeded"))
        except ValueError as exc:
            raise BusinessRuleError(
                message=f"invalid status: {exc}", code="RUN_STATUS_INVALID"
            ) from exc
        record = RunRecord.from_event(
            tenant_id=cmd["tenant_id"],
            workspace_id=cmd["workspace_id"],
            run_type=run_type,
            source_id=cmd.get("source_id"),
            completed_at=cmd.get("completed_at"),
            status=status,
            latency_ms=cmd.get("latency_ms"),
            actor_id=cmd.get("actor_id"),
            started_at=cmd.get("started_at"),
            metadata=cmd.get("metadata"),
        )
        return await service.run_repo.add(record)

    return execute


__all__ = ["build"]
