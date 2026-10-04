"""Get + List eval runs."""

from __future__ import annotations

from dataclasses import dataclass

from qzdap_schema.ids import (
    AgentTemplateId,
    AgentVersionId,
    EvalRunId,
    TenantId,
    WorkspaceId,
)

from qzdap.modules.evaluation.application.ports import EvalRunRepository
from qzdap.modules.evaluation.domain.entities import EvalRun
from qzdap.modules.evaluation.domain.errors import EvalRunNotFound


@dataclass(slots=True)
class GetEvalRunUseCase:
    repository: EvalRunRepository

    async def execute(self, *, tenant_id: TenantId, run_id: EvalRunId) -> EvalRun:
        run = await self.repository.get(tenant_id=tenant_id, run_id=run_id)
        if run is None:
            raise EvalRunNotFound(f"eval run {run_id} not found in tenant")
        return run


@dataclass(slots=True)
class ListEvalRunsUseCase:
    repository: EvalRunRepository

    async def execute(
        self,
        *,
        tenant_id: TenantId,
        workspace_id: WorkspaceId,
        template_id: AgentTemplateId | None = None,
        version_id: AgentVersionId | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[EvalRun]:
        return await self.repository.list_records(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            template_id=template_id,
            version_id=version_id,
            limit=limit,
            offset=offset,
        )


__all__ = ["GetEvalRunUseCase", "ListEvalRunsUseCase"]
