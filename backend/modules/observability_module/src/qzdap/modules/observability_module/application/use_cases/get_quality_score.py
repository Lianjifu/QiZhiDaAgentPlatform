"""get_quality_score — read-through aggregate of the latest passed eval run.

Not stored in ``observability_module`` own tables: we delegate to the
cross-module :class:`EvalRunQueryPort` (implemented by Evaluation's
adapter) and return whatever it produced.  When the port is not
configured (e.g. in tests) we return ``None`` and the HTTP layer maps
that to 404 QUALITY_NOT_FOUND.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from qzdap_schema.ids import (
    AgentTemplateId,
    AgentVersionId,
    TenantId,
)

if TYPE_CHECKING:
    from qzdap.modules.observability_module.application.services import (
        ObservabilityService,
    )


@dataclass(slots=True, frozen=True)
class QualityScore:
    template_id: AgentTemplateId
    version_id: AgentVersionId
    latest_eval_run_id: Any
    mean_score: float
    completed_at: datetime
    sample_count: int


def build(service: ObservabilityService) -> Any:
    async def execute(
        *,
        tenant_id: TenantId,
        template_id: AgentTemplateId,
        version_id: AgentVersionId,
    ) -> QualityScore | None:
        if service.eval_query is None:
            return None
        run = await service.eval_query.latest_passed_run(
            tenant_id=tenant_id,
            template_id=template_id,
            version_id=version_id,
        )
        if run is None:
            return None
        # run is whatever EvalRunRepository returns (typed in P8); we
        # only read three attributes, so duck-typed access keeps this
        # module decoupled from evaluation's domain.
        return QualityScore(
            template_id=template_id,
            version_id=version_id,
            latest_eval_run_id=getattr(run, "id", None),
            mean_score=float(getattr(run, "mean_score", 0.0)),
            completed_at=getattr(run, "completed_at", datetime.now(UTC)),
            sample_count=int(getattr(run, "sample_count", 0)),
        )

    return execute


__all__ = ["QualityScore", "build"]
