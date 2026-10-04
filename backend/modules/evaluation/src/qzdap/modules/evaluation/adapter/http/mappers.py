"""Entity → HTTP DTO mappers for the evaluation module."""

from __future__ import annotations

from qzdap.modules.evaluation.adapter.http.dto import (
    CaseResponse,
    DatasetResponse,
    RunResponse,
)
from qzdap.modules.evaluation.domain.entities import (
    EvalCase,
    EvalDataset,
    EvalRun,
)


def dataset_to_dto(entity: EvalDataset) -> DatasetResponse:
    return DatasetResponse(
        id=entity.id,
        tenant_id=entity.tenant_id,
        workspace_id=entity.workspace_id,
        name=entity.name,
        description=entity.description,
        kind=entity.kind.value,
        status=entity.status.value,
        case_count=entity.case_count,
        metadata=dict(entity.metadata),
        created_by=entity.created_by,
        created_at=entity.created_at,
        updated_at=entity.updated_at,
    )


def case_to_dto(entity: EvalCase) -> CaseResponse:
    return CaseResponse(
        id=entity.id,
        tenant_id=entity.tenant_id,
        workspace_id=entity.workspace_id,
        dataset_id=entity.dataset_id,
        ordinal=entity.ordinal,
        input=entity.input,
        expected_keywords=entity.expected_keywords,
        min_keywords_hit_ratio=entity.min_keywords_hit_ratio,
        max_latency_ms=entity.max_latency_ms,
        metadata=dict(entity.metadata),
        created_at=entity.created_at,
        updated_at=entity.updated_at,
    )


def run_to_dto(entity: EvalRun) -> RunResponse:
    return RunResponse(
        id=entity.id,
        tenant_id=entity.tenant_id,
        workspace_id=entity.workspace_id,
        dataset_id=entity.dataset_id,
        template_id=entity.template_id,
        version_id=entity.version_id,
        status=entity.status.value,
        mean_score=entity.mean_score,
        case_count=entity.case_count,
        passed_count=entity.passed_count,
        failed_count=entity.failed_count,
        started_at=entity.started_at,
        completed_at=entity.completed_at,
        error_message=entity.error_message,
        idempotency_key=entity.idempotency_key,
        triggered_by=entity.triggered_by,
        created_at=entity.created_at,
        updated_at=entity.updated_at,
    )


__all__ = [
    "case_to_dto",
    "dataset_to_dto",
    "run_to_dto",
]
