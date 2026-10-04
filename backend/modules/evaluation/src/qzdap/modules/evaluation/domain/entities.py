"""Evaluation module entities.

Four aggregate roots:

- :class:`EvalDataset` — named, tenant-scoped collection of cases.  The
  ``kind`` column distinguishes ``builtin`` (shipped 50-case golden
  dataset, seeded at first boot) from ``custom`` (uploaded JSON).
- :class:`EvalCase`     — one row of the dataset: prompt + expected
  keywords + min-hit-ratio + max-latency threshold.
- :class:`EvalRun`      — one execution of a dataset against an
  ``(AgentTemplate, AgentVersion)`` pair.  Carries status + mean_score +
  passed/failed counts + idempotency_key.
- :class:`EvalScoreRecord` — pure-data one-row-per-case score (kept in
  memory / emitted on the event bus; not its own table — see
  ``0012_evaluation``).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

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

from qzdap.modules.evaluation.domain.value_objects import (
    MAX_DESCRIPTION_LEN,
    MAX_INPUT_LEN,
    MAX_KEYWORD_LEN,
    MAX_KEYWORDS,
    MAX_NAME_LEN,
    EvalDatasetKind,
    EvalDatasetStatus,
    EvalRunStatus,
)


def _utcnow() -> datetime:
    return datetime.now(UTC)


# ── EvalDataset ──────────────────────────────────────────────────────────


@dataclass(slots=True, frozen=True)
class EvalDataset:
    id: EvalDatasetId
    tenant_id: TenantId
    workspace_id: WorkspaceId
    name: str
    description: str
    kind: EvalDatasetKind
    status: EvalDatasetStatus
    case_count: int
    metadata: dict[str, Any]
    created_by: UserId
    created_at: datetime
    updated_at: datetime

    @classmethod
    def create(
        cls,
        *,
        tenant_id: TenantId,
        workspace_id: WorkspaceId,
        name: str,
        description: str,
        kind: EvalDatasetKind,
        case_count: int,
        metadata: dict[str, Any] | None = None,
        created_by: UserId,
        dataset_id: EvalDatasetId | None = None,
        now: datetime | None = None,
    ) -> EvalDataset:
        if not name or not name.strip():
            raise ValueError("EvalDataset.name must be non-empty")
        if len(name) > MAX_NAME_LEN:
            raise ValueError(
                f"EvalDataset.name must be <= {MAX_NAME_LEN} chars, got {len(name)}"
            )
        if len(description) > MAX_DESCRIPTION_LEN:
            raise ValueError(
                f"EvalDataset.description must be <= {MAX_DESCRIPTION_LEN} chars"
            )
        if case_count < 0:
            raise ValueError("EvalDataset.case_count must be >= 0")
        ts = now or _utcnow()
        return cls(
            id=dataset_id or EvalDatasetId(uuid4()),
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            name=name,
            description=description,
            kind=kind,
            status=EvalDatasetStatus.ACTIVE,
            case_count=case_count,
            metadata=dict(metadata or {}),
            created_by=created_by,
            created_at=ts,
            updated_at=ts,
        )

    def with_status(
        self, status: EvalDatasetStatus, *, now: datetime | None = None
    ) -> EvalDataset:
        ts = now or _utcnow()
        return EvalDataset(
            id=self.id,
            tenant_id=self.tenant_id,
            workspace_id=self.workspace_id,
            name=self.name,
            description=self.description,
            kind=self.kind,
            status=status,
            case_count=self.case_count,
            metadata=self.metadata,
            created_by=self.created_by,
            created_at=self.created_at,
            updated_at=ts,
        )


# ── EvalCase ─────────────────────────────────────────────────────────────


@dataclass(slots=True, frozen=True)
class EvalCase:
    id: EvalCaseId
    tenant_id: TenantId
    workspace_id: WorkspaceId
    dataset_id: EvalDatasetId
    ordinal: int
    input: str
    expected_keywords: tuple[str, ...]
    min_keywords_hit_ratio: float
    max_latency_ms: int
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime

    @classmethod
    def create(
        cls,
        *,
        tenant_id: TenantId,
        workspace_id: WorkspaceId,
        dataset_id: EvalDatasetId,
        ordinal: int,
        input: str,
        expected_keywords: tuple[str, ...] = (),
        min_keywords_hit_ratio: float = 0.6,
        max_latency_ms: int = 30_000,
        metadata: dict[str, Any] | None = None,
        case_id: EvalCaseId | None = None,
        now: datetime | None = None,
    ) -> EvalCase:
        if not input or not input.strip():
            raise ValueError("EvalCase.input must be non-empty")
        if len(input) > MAX_INPUT_LEN:
            raise ValueError(f"EvalCase.input must be <= {MAX_INPUT_LEN} chars")
        if len(expected_keywords) > MAX_KEYWORDS:
            raise ValueError(f"EvalCase.expected_keywords must be <= {MAX_KEYWORDS}")
        for kw in expected_keywords:
            if not kw or len(kw) > MAX_KEYWORD_LEN:
                raise ValueError(f"EvalCase keyword must be 1..{MAX_KEYWORD_LEN} chars")
        if not 0.0 <= min_keywords_hit_ratio <= 1.0:
            raise ValueError("EvalCase.min_keywords_hit_ratio must be in [0.0, 1.0]")
        if max_latency_ms <= 0:
            raise ValueError("EvalCase.max_latency_ms must be > 0")
        ts = now or _utcnow()
        return cls(
            id=case_id or EvalCaseId(uuid4()),
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            dataset_id=dataset_id,
            ordinal=ordinal,
            input=input,
            expected_keywords=tuple(expected_keywords),
            min_keywords_hit_ratio=min_keywords_hit_ratio,
            max_latency_ms=max_latency_ms,
            metadata=dict(metadata or {}),
            created_at=ts,
            updated_at=ts,
        )


# ── EvalRun ─────────────────────────────────────────────────────────────


@dataclass(slots=True, frozen=True)
class EvalRun:
    id: EvalRunId
    tenant_id: TenantId
    workspace_id: WorkspaceId
    dataset_id: EvalDatasetId
    template_id: AgentTemplateId
    version_id: AgentVersionId
    status: EvalRunStatus
    mean_score: float | None
    case_count: int
    passed_count: int
    failed_count: int
    started_at: datetime | None
    completed_at: datetime | None
    error_message: str | None
    idempotency_key: str | None
    triggered_by: UserId
    created_at: datetime
    updated_at: datetime

    @classmethod
    def queue(
        cls,
        *,
        tenant_id: TenantId,
        workspace_id: WorkspaceId,
        dataset_id: EvalDatasetId,
        template_id: AgentTemplateId,
        version_id: AgentVersionId,
        case_count: int,
        idempotency_key: str | None = None,
        triggered_by: UserId,
        run_id: EvalRunId | None = None,
        now: datetime | None = None,
    ) -> EvalRun:
        if case_count <= 0:
            raise ValueError("EvalRun.case_count must be > 0")
        ts = now or _utcnow()
        return cls(
            id=run_id or EvalRunId(uuid4()),
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            dataset_id=dataset_id,
            template_id=template_id,
            version_id=version_id,
            status=EvalRunStatus.QUEUED,
            mean_score=None,
            case_count=case_count,
            passed_count=0,
            failed_count=0,
            started_at=None,
            completed_at=None,
            error_message=None,
            idempotency_key=idempotency_key,
            triggered_by=triggered_by,
            created_at=ts,
            updated_at=ts,
        )

    def mark_running(self, *, now: datetime | None = None) -> EvalRun:
        ts = now or _utcnow()
        if self.status is not EvalRunStatus.QUEUED:
            from qzdap.modules.evaluation.domain.errors import EvaluationError

            raise EvaluationError(
                f"cannot mark running from status={self.status.value!r}"
            )
        return _replace(
            self, status=EvalRunStatus.RUNNING, started_at=ts, updated_at=ts
        )

    def mark_completed(
        self,
        *,
        mean_score: float,
        passed_count: int,
        failed_count: int,
        threshold: float,
        now: datetime | None = None,
    ) -> EvalRun:
        ts = now or _utcnow()
        # Gate is "passed" iff every case passed AND mean_score >= threshold.
        all_passed = failed_count == 0 and passed_count == self.case_count
        new_status = (
            EvalRunStatus.PASSED
            if all_passed and mean_score >= threshold
            else EvalRunStatus.FAILED
        )
        return _replace(
            self,
            status=new_status,
            mean_score=mean_score,
            passed_count=passed_count,
            failed_count=failed_count,
            completed_at=ts,
            updated_at=ts,
        )

    def mark_errored(
        self, *, error_message: str, now: datetime | None = None
    ) -> EvalRun:
        ts = now or _utcnow()
        return _replace(
            self,
            status=EvalRunStatus.ERRORED,
            error_message=error_message,
            completed_at=ts,
            updated_at=ts,
        )


def _replace(entity: EvalRun, **changes: Any) -> EvalRun:
    """Frozen-dataclass safe copy with overrides (avoids dataclasses.replace)."""
    import dataclasses

    return dataclasses.replace(entity, **changes)


# ── EvalScoreRecord ──────────────────────────────────────────────────────


@dataclass(slots=True, frozen=True)
class EvalScoreRecord:
    """Per-case score, kept in memory + emitted on the event bus.

    Not a separate SQL table — P8 emits them on the bus so P5 audit_log
    captures them as JSONB.
    """

    run_id: EvalRunId
    case_id: EvalCaseId
    input: str
    output: str
    matched_keywords: tuple[str, ...]
    missing_keywords: tuple[str, ...]
    keyword_hit_ratio: float
    latency_ms: int
    passed: bool
    error_message: str | None


__all__ = [
    "EvalCase",
    "EvalDataset",
    "EvalRun",
    "EvalScoreRecord",
]
