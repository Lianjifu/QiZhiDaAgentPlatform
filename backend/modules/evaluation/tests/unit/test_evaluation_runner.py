"""Tests for the EvalRunner + StartEvalRunUseCase."""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest
from _evaluation_unit_in_memory import (  # type: ignore[import-not-found]
    FakeSubAgentPort,
    InMemoryEvalDatasetRepository,
    InMemoryEvalRunRepository,
    RecordingPublisher,
    make_case,
    make_dataset,
)
from qzdap_schema.ids import (
    AgentTemplateId,
    AgentVersionId,
    EvalRunId,
    TenantId,
    UserId,
    WorkspaceId,
)

from qzdap.modules.evaluation.application.runner import EvalRunner
from qzdap.modules.evaluation.application.services import EvaluationService
from qzdap.modules.evaluation.domain.value_objects import EvalRunStatus

_TENANT = TenantId(uuid4())
_WORKSPACE = WorkspaceId(uuid4())
_USER = UserId(uuid4())
_TEMPLATE = AgentTemplateId(uuid4())
_VERSION = AgentVersionId(uuid4())


async def _wait_for_terminal(
    repo: InMemoryEvalRunRepository,
    tenant_id: TenantId,
    run_id: EvalRunId,
    timeout: float = 3.0,
):
    """Block until the run reaches a terminal status or the test times out."""
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        run = await repo.get(tenant_id=tenant_id, run_id=run_id)
        if run is not None and run.status in {
            EvalRunStatus.PASSED,
            EvalRunStatus.FAILED,
            EvalRunStatus.ERRORED,
        }:
            return run
        await asyncio.sleep(0.01)
    raise AssertionError(f"run {run_id} did not reach terminal status in {timeout}s")


def _service(
    *,
    responses: dict[str, str] | None = None,
    threshold: float = 0.6,
) -> tuple[
    EvaluationService,
    InMemoryEvalDatasetRepository,
    InMemoryEvalRunRepository,
    FakeSubAgentPort,
    RecordingPublisher,
]:
    ds_repo = InMemoryEvalDatasetRepository()
    run_repo = InMemoryEvalRunRepository()
    sub_agent = FakeSubAgentPort(responses=responses or {})
    pub = RecordingPublisher()
    runner = EvalRunner(
        run_repo=run_repo,
        dataset_repo=ds_repo,
        sub_agent=sub_agent,
        publisher=pub,
        scoring_threshold=threshold,
        concurrency=2,
    )
    svc = EvaluationService.from_parts(
        dataset_repository=ds_repo,
        run_repository=run_repo,
        runner=runner,
        publisher=pub,
    )
    return svc, ds_repo, run_repo, sub_agent, pub


@pytest.mark.asyncio
async def test_runner_passes_when_all_cases_match() -> None:
    svc, ds_repo, run_repo, _sub, pub = _service(
        responses={
            "say hello": "Hello there!",
            "say world": "World of agents!",
        }
    )
    ds = make_dataset()
    await ds_repo.add(ds)
    await ds_repo.add_case(
        make_case(
            dataset_id=ds.id,
            tenant_id=ds.tenant_id,
            workspace_id=ds.workspace_id,
            ordinal=1,
            input="say hello",
            expected_keywords=("hello",),
        )
    )
    await ds_repo.add_case(
        make_case(
            dataset_id=ds.id,
            tenant_id=ds.tenant_id,
            workspace_id=ds.workspace_id,
            ordinal=2,
            input="say world",
            expected_keywords=("world",),
        )
    )
    run = await svc.start_run.execute(
        tenant_id=ds.tenant_id,
        workspace_id=ds.workspace_id,
        dataset_id=ds.id,
        template_id=_TEMPLATE,
        version_id=_VERSION,
        triggered_by=_USER,
    )
    completed = await _wait_for_terminal(run_repo, ds.tenant_id, run.id)
    assert completed.status is EvalRunStatus.PASSED
    assert completed.passed_count == 2
    assert completed.failed_count == 0
    assert completed.mean_score == pytest.approx(1.0)
    # EvalRunStarted + EvalRunCompleted were emitted
    topics = [getattr(e, "TOPIC", "") for e in pub.published]
    assert "evaluation.run.started" in topics
    assert "evaluation.run.completed" in topics


@pytest.mark.asyncio
async def test_runner_fails_when_any_case_missing_keyword() -> None:
    svc, ds_repo, run_repo, _sub, _pub = _service(
        responses={"q1": "yes", "q2": "no relevant content"}
    )
    ds = make_dataset()
    await ds_repo.add(ds)
    await ds_repo.add_case(
        make_case(
            dataset_id=ds.id,
            tenant_id=ds.tenant_id,
            workspace_id=ds.workspace_id,
            ordinal=1,
            input="q1",
            expected_keywords=("yes",),
        )
    )
    await ds_repo.add_case(
        make_case(
            dataset_id=ds.id,
            tenant_id=ds.tenant_id,
            workspace_id=ds.workspace_id,
            ordinal=2,
            input="q2",
            expected_keywords=("EXPECTED",),
        )
    )
    run = await svc.start_run.execute(
        tenant_id=ds.tenant_id,
        workspace_id=ds.workspace_id,
        dataset_id=ds.id,
        template_id=_TEMPLATE,
        version_id=_VERSION,
        triggered_by=_USER,
    )
    completed = await _wait_for_terminal(run_repo, ds.tenant_id, run.id)
    assert completed.status is EvalRunStatus.FAILED
    assert completed.passed_count == 1
    assert completed.failed_count == 1


@pytest.mark.asyncio
async def test_runner_app_error_per_case_does_not_abort_run() -> None:
    """A single broken case becomes a 0-score record; the rest run."""

    class FlakySubAgent(FakeSubAgentPort):
        async def run_turn_to_completion(self, **kwargs):  # type: ignore[no-untyped-def]
            if kwargs["user_input"] == "boom":
                from qzdap_kernel.errors import ExternalServiceError

                raise ExternalServiceError("upstream timeout")
            return await super().run_turn_to_completion(**kwargs)

    ds_repo = InMemoryEvalDatasetRepository()
    run_repo = InMemoryEvalRunRepository()
    sub = FlakySubAgent(responses={"ok": "result ok"})
    pub = RecordingPublisher()
    runner = EvalRunner(
        run_repo=run_repo,
        dataset_repo=ds_repo,
        sub_agent=sub,
        publisher=pub,
    )
    svc = EvaluationService.from_parts(
        dataset_repository=ds_repo,
        run_repository=run_repo,
        runner=runner,
        publisher=pub,
    )
    ds = make_dataset()
    await ds_repo.add(ds)
    await ds_repo.add_case(
        make_case(
            dataset_id=ds.id,
            tenant_id=ds.tenant_id,
            workspace_id=ds.workspace_id,
            ordinal=1,
            input="ok",
            expected_keywords=("result",),
        )
    )
    await ds_repo.add_case(
        make_case(
            dataset_id=ds.id,
            tenant_id=ds.tenant_id,
            workspace_id=ds.workspace_id,
            ordinal=2,
            input="boom",
            expected_keywords=("anything",),
        )
    )
    run = await svc.start_run.execute(
        tenant_id=ds.tenant_id,
        workspace_id=ds.workspace_id,
        dataset_id=ds.id,
        template_id=_TEMPLATE,
        version_id=_VERSION,
        triggered_by=_USER,
    )
    completed = await _wait_for_terminal(run_repo, ds.tenant_id, run.id)
    # any error → run is FAILED but the runner kept going
    assert completed.status is EvalRunStatus.FAILED
    assert completed.failed_count == 2


@pytest.mark.asyncio
async def test_start_run_idempotent_returns_prior_run() -> None:
    svc, ds_repo, *_ = _service(responses={"q1": "q1"})
    ds = make_dataset()
    await ds_repo.add(ds)
    await ds_repo.add_case(
        make_case(
            dataset_id=ds.id,
            tenant_id=ds.tenant_id,
            workspace_id=ds.workspace_id,
            ordinal=1,
            input="q1",
            expected_keywords=("q1",),
        )
    )
    first = await svc.start_run.execute(
        tenant_id=ds.tenant_id,
        workspace_id=ds.workspace_id,
        dataset_id=ds.id,
        template_id=_TEMPLATE,
        version_id=_VERSION,
        triggered_by=_USER,
        idempotency_key="abc",
    )
    second = await svc.start_run.execute(
        tenant_id=ds.tenant_id,
        workspace_id=ds.workspace_id,
        dataset_id=ds.id,
        template_id=_TEMPLATE,
        version_id=_VERSION,
        triggered_by=_USER,
        idempotency_key="abc",
    )
    assert first.id == second.id


@pytest.mark.asyncio
async def test_runner_marks_errored_when_dataset_empty() -> None:
    svc, ds_repo, run_repo, _sub, _pub = _service()
    ds = make_dataset()
    await ds_repo.add(ds)
    # No cases added!
    run = await svc.start_run.execute(
        tenant_id=ds.tenant_id,
        workspace_id=ds.workspace_id,
        dataset_id=ds.id,
        template_id=_TEMPLATE,
        version_id=_VERSION,
        triggered_by=_USER,
    )
    errored = await _wait_for_terminal(run_repo, ds.tenant_id, run.id)
    assert errored.status is EvalRunStatus.ERRORED
    assert errored.error_message is not None
    assert "no cases" in errored.error_message.lower()


@pytest.mark.asyncio
async def test_get_run_unknown_returns_404() -> None:
    from qzdap.modules.evaluation.application.use_cases.get_run import (
        GetEvalRunUseCase,
    )
    from qzdap.modules.evaluation.domain.errors import EvalRunNotFound

    svc, _ds, run_repo, *_ = _service()
    uc: GetEvalRunUseCase = svc.get_run  # type: ignore[assignment]
    with pytest.raises(EvalRunNotFound):
        await uc.execute(tenant_id=_TENANT, run_id=EvalRunId(uuid4()))
    _ = run_repo  # keep linter happy


@pytest.mark.asyncio
async def test_list_runs_filters_by_template_and_version() -> None:
    svc, ds_repo, *_ = _service()
    ds = make_dataset()
    await ds_repo.add(ds)
    await ds_repo.add_case(
        make_case(
            dataset_id=ds.id,
            tenant_id=ds.tenant_id,
            workspace_id=ds.workspace_id,
            ordinal=1,
            input="x",
            expected_keywords=("x",),
        )
    )
    other_template = AgentTemplateId(uuid4())
    other_version = AgentVersionId(uuid4())
    run1 = await svc.start_run.execute(
        tenant_id=ds.tenant_id,
        workspace_id=ds.workspace_id,
        dataset_id=ds.id,
        template_id=_TEMPLATE,
        version_id=_VERSION,
        triggered_by=_USER,
    )
    run2 = await svc.start_run.execute(
        tenant_id=ds.tenant_id,
        workspace_id=ds.workspace_id,
        dataset_id=ds.id,
        template_id=other_template,
        version_id=other_version,
        triggered_by=_USER,
    )
    rows = await svc.list_runs.execute(  # type: ignore[union-attr]
        tenant_id=ds.tenant_id,
        workspace_id=ds.workspace_id,
        template_id=_TEMPLATE,
        version_id=_VERSION,
    )
    ids = {r.id for r in rows}
    assert run1.id in ids
    assert run2.id not in ids


__all__ = []
