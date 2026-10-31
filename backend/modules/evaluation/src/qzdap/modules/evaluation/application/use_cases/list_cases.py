"""List the cases of one eval dataset."""

from __future__ import annotations

from dataclasses import dataclass

from qzdap.modules.evaluation.application.ports import EvalDatasetRepository
from qzdap.modules.evaluation.domain.entities import EvalCase
from qzdap_kernel.ids import EvalDatasetId, TenantId


@dataclass(slots=True)
class ListEvalCasesUseCase:
    """**列一个数据集下的评测用例** ✓。

    ⚠️ **端点一直缺这个用例** ✓ —— `GET /datasets/{did}/cases` 直接取
    `svc.list_cases` ✓ —— 服务上**没有这个属性** ✗✗ → 那个端点**必然 500** ✗✗
    （P-13 的 mypy 扫出来的真缺陷 ✓）。
    """

    repository: EvalDatasetRepository

    async def execute(self, *, tenant_id: TenantId, dataset_id: EvalDatasetId) -> list[EvalCase]:
        return await self.repository.list_cases(tenant_id=tenant_id, dataset_id=dataset_id)


__all__ = ["ListEvalCasesUseCase"]
