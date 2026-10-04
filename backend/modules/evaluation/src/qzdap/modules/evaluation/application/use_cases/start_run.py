"""StartEvalRunUseCase — queue an eval run + spawn the runner in background."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from qzdap_schema.ids import (
    AgentTemplateId,
    AgentVersionId,
    EvalDatasetId,
    EvalRunId,
    TenantId,
    UserId,
    WorkspaceId,
)

from qzdap.modules.evaluation.application.ports import (
    EvalDatasetRepository,
    EvalRunRepository,
)
from qzdap.modules.evaluation.domain.entities import EvalRun
from qzdap.modules.evaluation.domain.errors import (
    EvalDatasetNotFound,
    EvalRunNotFound,
    IdempotencyKeyConflict,
)


@dataclass(slots=True)
class StartEvalRunUseCase:
    dataset_repo: EvalDatasetRepository
    run_repo: EvalRunRepository
    runner: Any  # EvalRunner — typed structurally; not Protocol-bound.
    policy_guard: object | None = None

    async def execute(
        self,
        *,
        tenant_id: TenantId,
        workspace_id: WorkspaceId,
        dataset_id: EvalDatasetId,
        template_id: AgentTemplateId,
        version_id: AgentVersionId,
        triggered_by: UserId,
        idempotency_key: str | None = None,
    ) -> EvalRun:
        # ── policy gate (P5 reuse) ────────────────────────────────────
        if self.policy_guard is not None:
            from qzdap_vault.actor import ActorContext

            await self.policy_guard.check(  # type: ignore[attr-defined]
                actor=ActorContext(
                    tenant_id=tenant_id,
                    workspace_id=workspace_id,
                    principal_id=triggered_by,
                ),
                action="evaluation:run:start",
                resource={"dataset_id": str(dataset_id)},
            )

        # ── resolve dataset + case count ──────────────────────────────
        ds = await self.dataset_repo.get(tenant_id=tenant_id, dataset_id=dataset_id)
        if ds is None:
            raise EvalDatasetNotFound(f"eval dataset {dataset_id} not found in tenant")
        case_count = ds.case_count

        # ── idempotency: same key → return prior run ─────────────────
        if idempotency_key is not None:
            prior = await self.run_repo.get_by_idempotency_key(
                tenant_id=tenant_id, idempotency_key=idempotency_key
            )
            if prior is not None:
                if (
                    prior.dataset_id != dataset_id
                    or prior.template_id != template_id
                    or prior.version_id != version_id
                ):
                    raise IdempotencyKeyConflict(
                        f"idempotency_key {idempotency_key!r} already used "
                        "by a different (dataset, template, version) triple"
                    )
                return prior

        run = EvalRun.queue(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            dataset_id=dataset_id,
            template_id=template_id,
            version_id=version_id,
            case_count=case_count,
            idempotency_key=idempotency_key,
            triggered_by=triggered_by,
        )
        saved = await self.run_repo.add(run)

        # ── fire-and-forget background runner ────────────────────────
        asyncio.create_task(self.runner.run(tenant_id=tenant_id, run_id=saved.id))

        return saved


__all__ = ["StartEvalRunUseCase"]
_ = (EvalRunId, EvalRunNotFound)  # keep imports referenced for tooling
