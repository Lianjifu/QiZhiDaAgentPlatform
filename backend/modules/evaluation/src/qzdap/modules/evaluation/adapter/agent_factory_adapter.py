"""Evaluation adapter for the agent_factory module.

Implements the ``EvaluationQueryPort`` protocol declared by agent_factory.
The release endpoint asks ``latest_passed_run(template_id, version_id)``
and gates the release on the returned ``EvalRunSummary``.

Kept in the evaluation module (not agent_factory) so the dependency
direction stays one-way: agent_factory → evaluation port only.  This is
the P8-6 closed-loop seam.
"""

from __future__ import annotations

from uuid import UUID

from qzdap.modules.agent_factory.application.ports import (
    EvalRunSummary,
    EvaluationQueryPort,
)
from qzdap_schema.ids import (
    AgentTemplateId,
    AgentVersionId,
    TenantId,
    WorkspaceId,
)

from qzdap.modules.evaluation.application.ports import EvalRunRepository
from qzdap.modules.evaluation.domain.value_objects import EvalRunStatus


class EvaluationServiceAdapter(EvaluationQueryPort):
    """Implements agent_factory's EvaluationQueryPort via EvalRunRepository.

    Reads only — never mutates the run.  A passing run is one whose
    status is ``passed``, ``mean_score >= threshold`` and
    ``completed_at`` is set.  ``threshold`` is the agent_factory's gate
    floor (passed through the constructor so the caller keeps
    single-source-of-truth on settings).
    """

    def __init__(
        self,
        *,
        run_repository: EvalRunRepository,
        score_threshold: float = 0.6,
    ) -> None:
        self._repo = run_repository
        self._threshold = score_threshold

    async def latest_passed_run(
        self,
        *,
        tenant_id: TenantId,
        template_id: AgentTemplateId,
        version_id: AgentVersionId,
    ) -> EvalRunSummary | None:
        rows = await self._repo.list_records(
            tenant_id=tenant_id,
            workspace_id=_ZERO_WORKSPACE,
            template_id=template_id,
            version_id=version_id,
            limit=50,
            offset=0,
        )
        # P8 picks the most-recently-completed PASSED row that beats the
        # threshold.  Rows are already ordered by created_at DESC.
        candidates = [
            r
            for r in rows
            if r.status is EvalRunStatus.PASSED
            and r.mean_score is not None
            and r.mean_score >= self._threshold
            and r.completed_at is not None
        ]
        if not candidates:
            return None
        latest = candidates[0]
        return EvalRunSummary(
            run_id=latest.id,
            status=latest.status.value,
            mean_score=latest.mean_score,
            completed_at=latest.completed_at,
        )


# workspace_id is required by the repository signature but unused here —
# the candidate filter is (template_id, version_id) which is unique
# per template/version.  A zero UUID is sufficient; the WHERE clause
# further filters by template_id/version_id, eliminating cross-workspace
# leakage.
_ZERO_WORKSPACE = WorkspaceId(UUID("00000000-0000-0000-0000-000000000000"))


__all__ = ["EvaluationServiceAdapter"]
