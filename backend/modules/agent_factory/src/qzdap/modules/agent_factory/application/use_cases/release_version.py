"""ReleaseAgentVersionUseCase — gate-checked published → released transition.

This is the only place in agent_factory that touches the eval gate.
Order of checks:

1. ``policy_guard`` (P5 reuse; optional).
2. load :class:`AgentTemplate` + :class:`AgentVersion` (404 if missing).
3. version must be in ``PUBLISHED`` status — otherwise
   :class:`BusinessRuleError` (EVAL_GATE_FAILED, status=422).
4. ask :class:`EvaluationQueryPort` for the latest ``passed`` run on
   ``(template, version)``.  If none → EVAL_GATE_FAILED.
5. require ``run.mean_score ≥ threshold`` and ``completed_at`` set —
   otherwise EVAL_GATE_FAILED.
6. write the :class:`Release` row + flip the version to RELEASED.
7. publish :class:`AgentReleased` on the bus.

The 422 contract matches ``EVAL_GATE_FAILED`` — callers can retry once
the eval has been rerun and passes.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import uuid4

from qzdap_schema.ids import (
    AgentTemplateId,
    AgentVersionId,
    ReleaseId,
    TenantId,
    UserId,
    WorkspaceId,
)

from qzdap.modules.agent_factory.application.ports import (
    AgentFactoryEventPublisher,
    AgentTemplateRepository,
    AgentVersionRepository,
    EvaluationQueryPort,
    ReleaseRepository,
)
from qzdap.modules.agent_factory.domain.entities import (
    Release,
)
from qzdap.modules.agent_factory.domain.errors import (
    AgentTemplateNotFound,
    AgentVersionNotFound,
    EvalGateFailed,
)
from qzdap.modules.agent_factory.domain.events import AgentReleased
from qzdap.modules.agent_factory.domain.value_objects import AgentVersionStatus

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ReleaseAgentVersionUseCase:
    template_repository: AgentTemplateRepository
    version_repository: AgentVersionRepository
    release_repository: ReleaseRepository
    evaluation_query: EvaluationQueryPort
    publisher: AgentFactoryEventPublisher | None = None
    policy_guard: object | None = None
    eval_score_min: float = 0.6

    async def execute(
        self,
        *,
        tenant_id: TenantId,
        workspace_id: WorkspaceId,
        template_id: AgentTemplateId,
        version_id: AgentVersionId,
        released_by: UserId | None = None,
        notes: str = "",
        release_id: ReleaseId | None = None,
    ) -> Release:
        # ── 1. policy gate ──────────────────────────────────────────────
        if self.policy_guard is not None:
            from qzdap_vault.actor import ActorContext

            await self.policy_guard.check(  # type: ignore[attr-defined]
                actor=ActorContext(
                    tenant_id=tenant_id,
                    workspace_id=workspace_id,
                    principal_id=released_by,
                ),
                action="agent_factory:version:release",
                resource={
                    "template_id": str(template_id),
                    "version_id": str(version_id),
                },
            )

        # ── 2. load entities ────────────────────────────────────────────
        template = await self.template_repository.get(
            tenant_id=tenant_id, template_id=template_id
        )
        if template is None:
            raise AgentTemplateNotFound(
                f"agent template {template_id} not found in tenant"
            )
        version = await self.version_repository.get(
            tenant_id=tenant_id, version_id=version_id
        )
        if version is None:
            raise AgentVersionNotFound(
                f"agent version {version_id} not found in tenant"
            )

        # ── 3. status must be PUBLISHED ─────────────────────────────────
        if version.status is not AgentVersionStatus.PUBLISHED:
            raise EvalGateFailed(
                f"version {version.version_tag} is not published "
                f"(status={version.status.value!r})",
                code="EVAL_GATE_FAILED",
                status=422,
            )

        # ── 4. look up the latest passed eval run for (template, version) ─
        run = await self.evaluation_query.latest_passed_run(
            tenant_id=tenant_id,
            template_id=template_id,
            version_id=version_id,
        )
        if run is None:
            raise EvalGateFailed(
                f"no passed eval run for version {version.version_tag}",
                code="EVAL_GATE_FAILED",
                status=422,
            )

        # ── 5. require mean_score ≥ threshold + completed_at ───────────
        if not run.is_gate_passed(self.eval_score_min):
            score_str = f"{run.mean_score:.2f}" if run.mean_score is not None else "n/a"
            raise EvalGateFailed(
                f"eval run {run.id} score={score_str} < "
                f"threshold={self.eval_score_min:.2f} or not completed",
                code="EVAL_GATE_FAILED",
                status=422,
            )

        # ── 6. write release + flip version to RELEASED ─────────────────
        release = Release.create(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            template_id=template_id,
            version_id=version_id,
            eval_run_id=run.id,
            eval_score=run.mean_score,
            released_by=released_by or UserId(uuid4()),
            notes=notes,
            release_id=release_id,
        )
        saved_release = await self.release_repository.add(release)

        released_version = version.release()
        await self.version_repository.update(released_version)

        # ── 7. publish AgentReleased ────────────────────────────────────
        if self.publisher is not None:
            try:
                await self.publisher.publish(
                    AgentReleased(
                        release_id=saved_release.id,
                        template_id=saved_release.template_id,
                        version_id=saved_release.version_id,
                        tenant_id=saved_release.tenant_id,
                        workspace_id=saved_release.workspace_id,
                        eval_run_id=saved_release.eval_run_id,
                        eval_score=saved_release.eval_score,
                        released_by=saved_release.released_by,
                    )
                )
            except Exception:  # pragma: no cover - defensive
                logger.exception(
                    "publish AgentReleased failed for %s", saved_release.id
                )

        return saved_release


__all__ = ["ReleaseAgentVersionUseCase"]
