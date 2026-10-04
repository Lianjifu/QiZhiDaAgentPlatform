"""Domain → DTO mappers for the observability HTTP layer."""

from __future__ import annotations

from qzdap.modules.observability_module.adapter.http.dto import (
    CostRecordResponse,
    QualityScoreResponse,
    RunRecordResponse,
)
from qzdap.modules.observability_module.application.use_cases.get_quality_score import (
    QualityScore,
)
from qzdap.modules.observability_module.domain.entities import (
    CostRecord,
    RunRecord,
)


def run_record_to_dto(record: RunRecord) -> RunRecordResponse:
    return RunRecordResponse(
        id=str(record.id),
        tenant_id=str(record.tenant_id),
        workspace_id=str(record.workspace_id),
        run_type=record.run_type.value,
        source_id=str(record.source_id) if record.source_id else None,
        actor_id=str(record.actor_id) if record.actor_id else None,
        started_at=record.started_at.isoformat() if record.started_at else None,
        completed_at=record.completed_at.isoformat(),
        latency_ms=record.latency_ms,
        status=record.status.value,
        metadata=record.metadata,
        created_at=record.created_at.isoformat(),
    )


def cost_record_to_dto(record: CostRecord) -> CostRecordResponse:
    return CostRecordResponse(
        id=str(record.id),
        tenant_id=str(record.tenant_id),
        workspace_id=str(record.workspace_id),
        run_id=str(record.run_id),
        cost_type=record.cost_type.value,
        amount_usd=str(record.amount_usd),
        quantity=record.quantity,
        unit=record.unit,
        currency=record.currency,
        model_id=record.model_id,
        metadata=record.metadata,
        created_at=record.created_at.isoformat(),
    )


def quality_score_to_dto(score: QualityScore) -> QualityScoreResponse:
    return QualityScoreResponse(
        template_id=str(score.template_id),
        version_id=str(score.version_id),
        latest_eval_run_id=(
            str(score.latest_eval_run_id) if score.latest_eval_run_id else None
        ),
        mean_score=score.mean_score,
        sample_count=score.sample_count,
        completed_at=(score.completed_at.isoformat() if score.completed_at else None),
    )


__all__ = [
    "cost_record_to_dto",
    "quality_score_to_dto",
    "run_record_to_dto",
]
