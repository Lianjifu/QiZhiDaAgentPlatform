"""Domain tests for evaluation entities + heuristic scorer (no I/O)."""

from __future__ import annotations

from uuid import uuid4

import pytest
from qzdap_schema.ids import (
    EvalDatasetId,
    TenantId,
    UserId,
    WorkspaceId,
)

from qzdap.modules.evaluation.application.scoring import score_case
from qzdap.modules.evaluation.domain.entities import EvalCase, EvalDataset, EvalRun
from qzdap.modules.evaluation.domain.value_objects import (
    EvalDatasetKind,
    EvalDatasetStatus,
    EvalRunStatus,
)

_TENANT = TenantId(uuid4())
_WORKSPACE = WorkspaceId(uuid4())
_USER = UserId(uuid4())


def _now_iso():
    from datetime import UTC, datetime

    return datetime(2024, 1, 1, tzinfo=UTC)


def test_dataset_create_minimal() -> None:
    ds = EvalDataset.create(
        tenant_id=_TENANT,
        workspace_id=_WORKSPACE,
        name="golden-default",
        description="",
        kind=EvalDatasetKind.BUILTIN,
        case_count=50,
        created_by=_USER,
        now=_now_iso(),
    )
    assert ds.status is EvalDatasetStatus.ACTIVE
    assert ds.kind is EvalDatasetKind.BUILTIN
    assert ds.case_count == 50


def test_dataset_create_rejects_empty_name() -> None:
    with pytest.raises(ValueError):
        EvalDataset.create(
            tenant_id=_TENANT,
            workspace_id=_WORKSPACE,
            name="   ",
            description="",
            kind=EvalDatasetKind.CUSTOM,
            case_count=10,
            created_by=_USER,
        )


def test_dataset_with_status_round_trips() -> None:
    ds = EvalDataset.create(
        tenant_id=_TENANT,
        workspace_id=_WORKSPACE,
        name="d",
        description="",
        kind=EvalDatasetKind.CUSTOM,
        case_count=5,
        created_by=_USER,
        now=_now_iso(),
    )
    archived = ds.with_status(EvalDatasetStatus.ARCHIVED, now=_now_iso())
    assert archived.status is EvalDatasetStatus.ARCHIVED
    assert archived.created_at == ds.created_at


def test_case_create_validates_keywords() -> None:
    ds_id = EvalDatasetId(uuid4())
    base: dict[str, object] = {
        "tenant_id": _TENANT,
        "workspace_id": _WORKSPACE,
        "dataset_id": ds_id,
        "ordinal": 1,
        "input": "hello",
        "expected_keywords": ("foo", "bar"),
    }
    case = EvalCase.create(**base)
    assert case.expected_keywords == ("foo", "bar")
    assert case.min_keywords_hit_ratio == 0.6
    # empty input rejected
    with pytest.raises(ValueError):
        EvalCase.create(**{**base, "input": "  "})
    # bad ratio
    with pytest.raises(ValueError):
        EvalCase.create(**{**base, "min_keywords_hit_ratio": 1.5})


def test_run_queue_starts_in_queued_state() -> None:
    run = EvalRun.queue(
        tenant_id=_TENANT,
        workspace_id=_WORKSPACE,
        dataset_id=EvalDatasetId(uuid4()),
        template_id=__import__(
            "qzdap_schema.ids", fromlist=["AgentTemplateId"]
        ).AgentTemplateId(uuid4()),
        version_id=__import__(
            "qzdap_schema.ids", fromlist=["AgentVersionId"]
        ).AgentVersionId(uuid4()),
        case_count=10,
        triggered_by=_USER,
        now=_now_iso(),
    )
    assert run.status is EvalRunStatus.QUEUED
    assert run.mean_score is None
    assert run.started_at is None
    assert run.completed_at is None


def test_run_mark_running_then_computed() -> None:
    from qzdap_schema.ids import AgentTemplateId, AgentVersionId

    run = EvalRun.queue(
        tenant_id=_TENANT,
        workspace_id=_WORKSPACE,
        dataset_id=EvalDatasetId(uuid4()),
        template_id=AgentTemplateId(uuid4()),
        version_id=AgentVersionId(uuid4()),
        case_count=5,
        triggered_by=_USER,
        now=_now_iso(),
    )
    running = run.mark_running(now=_now_iso())
    assert running.status is EvalRunStatus.RUNNING
    assert running.started_at is not None

    completed = running.mark_completed(
        mean_score=0.85,
        passed_count=5,
        failed_count=0,
        threshold=0.6,
        now=_now_iso(),
    )
    assert completed.status is EvalRunStatus.PASSED
    assert completed.mean_score == 0.85
    assert completed.completed_at is not None


def test_run_mark_completed_any_failure_makes_failed() -> None:
    from qzdap_schema.ids import AgentTemplateId, AgentVersionId

    run = EvalRun.queue(
        tenant_id=_TENANT,
        workspace_id=_WORKSPACE,
        dataset_id=EvalDatasetId(uuid4()),
        template_id=AgentTemplateId(uuid4()),
        version_id=AgentVersionId(uuid4()),
        case_count=5,
        triggered_by=_USER,
        now=_now_iso(),
    )
    running = run.mark_running(now=_now_iso())
    completed = running.mark_completed(
        mean_score=0.9,  # above threshold
        passed_count=4,
        failed_count=1,
        threshold=0.6,
        now=_now_iso(),
    )
    assert completed.status is EvalRunStatus.FAILED


def test_run_mark_completed_below_threshold_is_failed() -> None:
    from qzdap_schema.ids import AgentTemplateId, AgentVersionId

    run = EvalRun.queue(
        tenant_id=_TENANT,
        workspace_id=_WORKSPACE,
        dataset_id=EvalDatasetId(uuid4()),
        template_id=AgentTemplateId(uuid4()),
        version_id=AgentVersionId(uuid4()),
        case_count=5,
        triggered_by=_USER,
        now=_now_iso(),
    )
    running = run.mark_running(now=_now_iso())
    completed = running.mark_completed(
        mean_score=0.3,
        passed_count=5,
        failed_count=0,
        threshold=0.6,
        now=_now_iso(),
    )
    assert completed.status is EvalRunStatus.FAILED


def test_run_mark_errored() -> None:
    from qzdap_schema.ids import AgentTemplateId, AgentVersionId

    run = EvalRun.queue(
        tenant_id=_TENANT,
        workspace_id=_WORKSPACE,
        dataset_id=EvalDatasetId(uuid4()),
        template_id=AgentTemplateId(uuid4()),
        version_id=AgentVersionId(uuid4()),
        case_count=5,
        triggered_by=_USER,
        now=_now_iso(),
    )
    running = run.mark_running(now=_now_iso())
    err = running.mark_errored(error_message="boom", now=_now_iso())
    assert err.status is EvalRunStatus.ERRORED
    assert err.error_message == "boom"


# ── heuristic scorer ────────────────────────────────────────────────────


def _make_case(*, kws=(), min_hit=0.6, max_lat=30_000) -> EvalCase:
    return EvalCase.create(
        tenant_id=_TENANT,
        workspace_id=_WORKSPACE,
        dataset_id=EvalDatasetId(uuid4()),
        ordinal=1,
        input="hello",
        expected_keywords=kws,
        min_keywords_hit_ratio=min_hit,
        max_latency_ms=max_lat,
    )


def test_score_all_keywords_hit_passes() -> None:
    case = _make_case(kws=("foo", "bar"), min_hit=0.6, max_lat=1000)
    s = score_case(case=case, output="Hello FOO and bar there", latency_ms=200)
    assert s.passed is True
    assert s.hit_ratio == 1.0
    assert set(s.matched) == {"foo", "bar"}


def test_score_partial_match_below_threshold_fails() -> None:
    case = _make_case(kws=("foo", "bar", "baz"), min_hit=0.6)
    s = score_case(case=case, output="only foo mentioned", latency_ms=200)
    assert s.passed is False
    assert s.hit_ratio == pytest.approx(1 / 3)


def test_score_latency_over_max_fails() -> None:
    case = _make_case(kws=("foo",), max_lat=500)
    s = score_case(case=case, output="foo here", latency_ms=999)
    assert s.passed is False


def test_score_error_immediately_fails() -> None:
    case = _make_case(kws=("foo",))
    s = score_case(case=case, output="", latency_ms=10, error="boom")
    assert s.passed is False
    assert s.error == "boom"


def test_score_case_insensitive() -> None:
    case = _make_case(kws=("foo",))
    s = score_case(case=case, output="FOO bar", latency_ms=10)
    assert s.matched == ("foo",)


__all__ = []
