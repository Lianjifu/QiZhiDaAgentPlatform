"""Heuristic scorer — pure function.

Each case is scored against the agent's output by:
  - substring matching each ``expected_keyword`` (case-insensitive)
  - computing ``hit_ratio = matched / len(expected_keywords)``
  - gating on ``latency_ms <= case.max_latency_ms``
  - emitting an :class:`EvalScoreRecord` with both raw inputs and the
    derived metrics.

No external I/O. Deterministic. Easy to test.
"""

from __future__ import annotations

from dataclasses import dataclass

from qzdap_schema.ids import EvalCaseId, EvalRunId

from qzdap.modules.evaluation.domain.entities import EvalCase, EvalScoreRecord


@dataclass(slots=True, frozen=True)
class CaseScore:
    """Result of scoring a single (case, output) pair."""

    matched: tuple[str, ...]
    missing: tuple[str, ...]
    hit_ratio: float
    latency_ms: int
    passed: bool
    error: str | None

    def to_record(
        self, *, run_id: EvalRunId, case: EvalCase, output: str
    ) -> EvalScoreRecord:
        return EvalScoreRecord(
            run_id=run_id,
            case_id=case.id,
            input=case.input,
            output=output,
            matched_keywords=self.matched,
            missing_keywords=self.missing,
            keyword_hit_ratio=self.hit_ratio,
            latency_ms=self.latency_ms,
            passed=self.passed,
            error_message=self.error,
        )


def score_case(
    *,
    case: EvalCase,
    output: str,
    latency_ms: int,
    error: str | None = None,
) -> CaseScore:
    """Pure scorer — case-insensitive keyword hit + latency gate.

    Pass criteria:
      - ``error`` is None
      - ``hit_ratio >= case.min_keywords_hit_ratio``
      - ``latency_ms <= case.max_latency_ms``
    """
    if error is not None:
        return CaseScore(
            matched=(),
            missing=tuple(case.expected_keywords),
            hit_ratio=0.0,
            latency_ms=latency_ms,
            passed=False,
            error=error,
        )
    out_lower = output.lower()
    matched: list[str] = []
    missing: list[str] = []
    for kw in case.expected_keywords:
        if kw.lower() in out_lower:
            matched.append(kw)
        else:
            missing.append(kw)
    total = len(case.expected_keywords)
    hit = len(matched) / max(total, 1)
    latency_ok = latency_ms <= case.max_latency_ms
    passed = hit >= case.min_keywords_hit_ratio and latency_ok
    return CaseScore(
        matched=tuple(matched),
        missing=tuple(missing),
        hit_ratio=hit,
        latency_ms=latency_ms,
        passed=passed,
        error=None,
    )


__all__ = [
    "CaseScore",
    "score_case",
]


_ = EvalCaseId  # type-only re-export to keep id imports tidy in callers
