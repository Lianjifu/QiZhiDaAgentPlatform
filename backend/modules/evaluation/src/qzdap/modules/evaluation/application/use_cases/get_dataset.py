"""Get + List eval datasets."""

from __future__ import annotations

from dataclasses import dataclass

from qzdap_schema.ids import EvalDatasetId, TenantId, WorkspaceId

from qzdap.modules.evaluation.application.ports import EvalDatasetRepository
from qzdap.modules.evaluation.domain.entities import EvalDataset
from qzdap.modules.evaluation.domain.errors import EvalDatasetNotFound


@dataclass(slots=True)
class GetEvalDatasetUseCase:
    repository: EvalDatasetRepository

    async def execute(
        self, *, tenant_id: TenantId, dataset_id: EvalDatasetId
    ) -> EvalDataset:
        ds = await self.repository.get(tenant_id=tenant_id, dataset_id=dataset_id)
        if ds is None:
            raise EvalDatasetNotFound(f"eval dataset {dataset_id} not found in tenant")
        return ds


@dataclass(slots=True)
class ListEvalDatasetsUseCase:
    repository: EvalDatasetRepository

    async def execute(
        self,
        *,
        tenant_id: TenantId,
        workspace_id: WorkspaceId,
        limit: int = 50,
        offset: int = 0,
    ) -> list[EvalDataset]:
        return await self.repository.list_records(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            limit=limit,
            offset=offset,
        )


__all__ = ["GetEvalDatasetUseCase", "ListEvalDatasetsUseCase"]
