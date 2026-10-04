"""Events emitted by the evaluation module."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from qzdap_kernel.events import DomainEvent
from qzdap_schema.ids import (
    AgentTemplateId,
    AgentVersionId,
    EvalDatasetId,
    EvalRunId,
    TenantId,
    UserId,
    WorkspaceId,
)


@dataclass(slots=True, frozen=True)
class EvalRunStarted(DomainEvent):
    """Emitted when an EvalRun transitions QUEUED → RUNNING."""

    TOPIC = "evaluation.run.started"

    run_id: EvalRunId
    tenant_id: TenantId
    workspace_id: WorkspaceId
    template_id: AgentTemplateId
    version_id: AgentVersionId
    dataset_id: EvalDatasetId
    case_count: int
    started_at: datetime
    triggered_by: UserId


@dataclass(slots=True, frozen=True)
class EvalRunCompleted(DomainEvent):
    """Emitted when an EvalRun reaches a terminal status."""

    TOPIC = "evaluation.run.completed"

    run_id: EvalRunId
    tenant_id: TenantId
    workspace_id: WorkspaceId
    template_id: AgentTemplateId
    version_id: AgentVersionId
    dataset_id: EvalDatasetId
    status: str  # passed | failed | errored
    mean_score: float | None
    passed_count: int
    failed_count: int
    completed_at: datetime
    scores: tuple[dict, ...]  # serialised EvalScoreRecord list


@dataclass(slots=True, frozen=True)
class EvalRunFailed(DomainEvent):
    """Emitted when the runner itself errors before completion."""

    TOPIC = "evaluation.run.failed"

    run_id: EvalRunId
    tenant_id: TenantId
    workspace_id: WorkspaceId
    error_code: str
    error_message: str
    failed_at: datetime


def _now() -> datetime:
    return datetime.now(UTC)


__all__ = [
    "EvalRunCompleted",
    "EvalRunFailed",
    "EvalRunStarted",
]
