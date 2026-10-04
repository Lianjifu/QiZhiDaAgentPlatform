"""EvalRunner — background task that drains an EvalRun across all cases.

Lifecycle:
  1. Loads the EvalRun + all cases in the dataset.
  2. Marks RUNNING + emits EvalRunStarted.
  3. Spawns ``asyncio.gather`` over every case with a Semaphore
     (concurrency=4 by default).
  4. Each case drives a fresh agent_runtime session through the
     SubAgentPort, captures latency, runs the heuristic scorer.
  5. Aggregates mean_score, passed_count, failed_count.
  6. Marks terminal status (PASSED/FAILED), emits EvalRunCompleted.

Errors raised by the SubAgentPort are caught per-case and converted into
a ``CaseScore(error=...)`` so a single broken case does not abort the
whole run.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any

from qzdap_kernel.errors import AppError

from qzdap.modules.evaluation.application.ports import (
    EvalRunRepository,
    SubAgentPort,
)
from qzdap.modules.evaluation.application.scoring import score_case
from qzdap.modules.evaluation.domain.entities import EvalCase, EvalRun
from qzdap.modules.evaluation.domain.events import (
    EvalRunCompleted,
    EvalRunFailed,
    EvalRunStarted,
)
from qzdap.modules.evaluation.domain.value_objects import EvalRunStatus

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class EvalRunner:
    """Background-task entrypoint. Not stateful across runs."""

    run_repo: EvalRunRepository
    dataset_repo: Any  # EvalDatasetRepository (typed via Protocol in use_cases)
    sub_agent: SubAgentPort
    publisher: Any  # EvaluationEventPublisher
    scoring_threshold: float = 0.6
    concurrency: int = 4
    case_timeout_seconds: float = 60.0

    async def run(
        self,
        *,
        tenant_id,  # TenantId
        run_id,  # EvalRunId
    ) -> None:
        run = await self.run_repo.get(tenant_id=tenant_id, run_id=run_id)
        if run is None:
            logger.warning("eval run %s disappeared before run()", run_id)
            return
        if run.status is not EvalRunStatus.QUEUED:
            logger.warning(
                "eval run %s already in status=%s; skipping",
                run_id,
                run.status.value,
            )
            return

        cases = await self.dataset_repo.list_cases(
            tenant_id=tenant_id, dataset_id=run.dataset_id
        )
        if not cases:
            await self._mark_errored(run, error_message="dataset has no cases")
            return

        # ── QUEUED → RUNNING ──────────────────────────────────────────
        running = run.mark_running()
        await self.run_repo.update(running)
        if self.publisher is not None:
            try:
                await self.publisher.publish(
                    EvalRunStarted(
                        run_id=running.id,
                        tenant_id=running.tenant_id,
                        workspace_id=running.workspace_id,
                        template_id=running.template_id,
                        version_id=running.version_id,
                        dataset_id=running.dataset_id,
                        case_count=len(cases),
                        started_at=running.started_at,  # type: ignore[arg-type]
                        triggered_by=running.triggered_by,
                    )
                )
            except Exception:  # pragma: no cover - defensive
                logger.exception("publish EvalRunStarted failed for %s", run.id)

        # ── score every case under a Semaphore ────────────────────────
        sem = asyncio.Semaphore(max(1, self.concurrency))

        async def _one(case: EvalCase) -> tuple[EvalCase, float, bool, int, str | None]:
            async with sem:
                t0 = time.monotonic()
                try:
                    result = await asyncio.wait_for(
                        self.sub_agent.run_turn_to_completion(
                            tenant_id=run.tenant_id,
                            workspace_id=run.workspace_id,
                            owner_id=run.triggered_by,
                            agent_id=run.template_id,
                            agent_version=run.version_id.hex,
                            user_input=case.input,
                            timeout_seconds=self.case_timeout_seconds,
                        ),
                        timeout=self.case_timeout_seconds,
                    )
                except TimeoutError:
                    return (
                        case,
                        0.0,
                        False,
                        int((time.monotonic() - t0) * 1000),
                        f"timeout after {self.case_timeout_seconds:.1f}s",
                    )
                except AppError as exc:
                    return (
                        case,
                        0.0,
                        False,
                        int((time.monotonic() - t0) * 1000),
                        f"{exc.__class__.__name__}: {exc}",
                    )
                except Exception as exc:  # noqa: BLE001
                    return (
                        case,
                        0.0,
                        False,
                        int((time.monotonic() - t0) * 1000),
                        f"unexpected: {exc}",
                    )
                output = str(result.get("final_message") or "")
                latency_ms = int((time.monotonic() - t0) * 1000)
                score = score_case(case=case, output=output, latency_ms=latency_ms)
                return (case, score.hit_ratio, score.passed, latency_ms, None)

        try:
            raw = await asyncio.gather(*(_one(c) for c in cases))
        except Exception as exc:  # noqa: BLE001 - total runner failure
            await self._mark_errored(running, error_message=f"runner crashed: {exc}")
            return

        # ── aggregate ─────────────────────────────────────────────────
        mean_score = sum(r[1] for r in raw) / max(len(raw), 1)
        passed_count = sum(1 for r in raw if r[2])
        failed_count = len(raw) - passed_count
        case_errors = [(c, err) for (c, _h, _p, _l, err) in raw if err is not None]
        # an errored case is also a "failed" case for scoring purposes.
        if case_errors:
            failed_count = len(raw)  # any error → run fails
            passed_count = 0

        completed = running.mark_completed(
            mean_score=mean_score,
            passed_count=passed_count,
            failed_count=failed_count,
            threshold=self.scoring_threshold,
        )
        await self.run_repo.update(completed)

        # ── emit EvalRunCompleted with serialised score records ───────
        if self.publisher is not None:
            score_dicts = []
            for case, hit, passed, latency, err in raw:
                score_dicts.append(
                    {
                        "case_id": str(case.id),
                        "input": case.input,
                        "output": "",  # never log agent output verbatim
                        "keyword_hit_ratio": hit,
                        "latency_ms": latency,
                        "passed": passed,
                        "error_message": err,
                    }
                )
            try:
                await self.publisher.publish(
                    EvalRunCompleted(
                        run_id=completed.id,
                        tenant_id=completed.tenant_id,
                        workspace_id=completed.workspace_id,
                        template_id=completed.template_id,
                        version_id=completed.version_id,
                        dataset_id=completed.dataset_id,
                        status=completed.status.value,
                        mean_score=completed.mean_score,
                        passed_count=completed.passed_count,
                        failed_count=completed.failed_count,
                        completed_at=completed.completed_at,  # type: ignore[arg-type]
                        scores=tuple(score_dicts),
                    )
                )
            except Exception:  # pragma: no cover - defensive
                logger.exception("publish EvalRunCompleted failed for %s", completed.id)

    async def _mark_errored(self, run: EvalRun, *, error_message: str) -> None:
        errored = run.mark_errored(error_message=error_message)
        try:
            await self.run_repo.update(errored)
        except Exception:  # pragma: no cover - defensive
            logger.exception("failed to persist errored run %s", run.id)
        if self.publisher is not None:
            try:
                await self.publisher.publish(
                    EvalRunFailed(
                        run_id=errored.id,
                        tenant_id=errored.tenant_id,
                        workspace_id=errored.workspace_id,
                        error_code="RUNNER_ERROR",
                        error_message=error_message,
                        failed_at=errored.completed_at or errored.updated_at,  # type: ignore[arg-type]
                    )
                )
            except Exception:  # pragma: no cover - defensive
                logger.exception("publish EvalRunFailed failed for %s", errored.id)


__all__ = ["EvalRunner"]
