"""Domain ↔ ORM mappers for the evaluation module.

Pure functions; SQL repositories call these from inside the session.
"""

from __future__ import annotations

from qzdap_schema.ids import (
    AgentTemplateId,
    AgentVersionId,
    EvalCaseId,
    EvalDatasetId,
    EvalRunId,
    TenantId,
    UserId,
    WorkspaceId,
)

from qzdap.modules.evaluation.adapter.persistence.models import (
    EvalCaseORM,
    EvalDatasetORM,
    EvalRunORM,
)
from qzdap.modules.evaluation.domain.entities import (
    EvalCase,
    EvalDataset,
    EvalRun,
)
from qzdap.modules.evaluation.domain.value_objects import (
    EvalDatasetKind,
    EvalDatasetStatus,
    EvalRunStatus,
)

# ── EvalDataset ──────────────────────────────────────────────────────────


def dataset_to_domain(row: EvalDatasetORM) -> EvalDataset:
    return EvalDataset(
        id=EvalDatasetId(row.id),
        tenant_id=TenantId(row.tenant_id),
        workspace_id=WorkspaceId(row.workspace_id),
        name=row.name,
        description=row.description or "",
        kind=EvalDatasetKind(row.kind),
        status=EvalDatasetStatus(row.status),
        case_count=row.case_count,
        metadata=dict(row.metadata_ or {}),
        created_by=UserId(row.created_by) if row.created_by else UserId(row.id),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def dataset_to_orm(entity: EvalDataset) -> EvalDatasetORM:
    return EvalDatasetORM(
        id=entity.id,
        tenant_id=entity.tenant_id,
        workspace_id=entity.workspace_id,
        name=entity.name,
        description=entity.description,
        kind=entity.kind.value,
        status=entity.status.value,
        case_count=entity.case_count,
        metadata_=dict(entity.metadata),
        created_by=entity.created_by,
        created_at=entity.created_at,
        updated_at=entity.updated_at,
    )


# ── EvalCase ──────────────────────────────────────────────────────────────


def case_to_domain(row: EvalCaseORM) -> EvalCase:
    return EvalCase(
        id=EvalCaseId(row.id),
        tenant_id=TenantId(row.tenant_id),
        workspace_id=WorkspaceId(row.workspace_id),
        dataset_id=EvalDatasetId(row.dataset_id),
        ordinal=row.ordinal,
        input=row.input,
        expected_keywords=tuple(row.expected_keywords or []),
        min_keywords_hit_ratio=float(row.min_keywords_hit_ratio),
        max_latency_ms=row.max_latency_ms,
        metadata=dict(row.metadata_ or {}),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def case_to_orm(entity: EvalCase) -> EvalCaseORM:
    return EvalCaseORM(
        id=entity.id,
        tenant_id=entity.tenant_id,
        workspace_id=entity.workspace_id,
        dataset_id=entity.dataset_id,
        ordinal=entity.ordinal,
        input=entity.input,
        expected_keywords=list(entity.expected_keywords),
        min_keywords_hit_ratio=entity.min_keywords_hit_ratio,
        max_latency_ms=entity.max_latency_ms,
        metadata_=dict(entity.metadata),
        created_at=entity.created_at,
        updated_at=entity.updated_at,
    )


# ── EvalRun ───────────────────────────────────────────────────────────────


def run_to_domain(row: EvalRunORM) -> EvalRun:
    return EvalRun(
        id=EvalRunId(row.id),
        tenant_id=TenantId(row.tenant_id),
        workspace_id=WorkspaceId(row.workspace_id),
        dataset_id=EvalDatasetId(row.dataset_id),
        template_id=AgentTemplateId(row.template_id),
        version_id=AgentVersionId(row.version_id),
        status=EvalRunStatus(row.status),
        mean_score=float(row.mean_score) if row.mean_score is not None else None,
        case_count=row.case_count,
        passed_count=row.passed_count,
        failed_count=row.failed_count,
        started_at=row.started_at,
        completed_at=row.completed_at,
        error_message=row.error_message,
        idempotency_key=row.idempotency_key,
        triggered_by=UserId(row.triggered_by) if row.triggered_by else UserId(row.id),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def run_to_orm(entity: EvalRun) -> EvalRunORM:
    return EvalRunORM(
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
    "case_to_domain",
    "case_to_orm",
    "dataset_to_domain",
    "dataset_to_orm",
    "run_to_domain",
    "run_to_orm",
]
