"""**淘汰**的模块侧实现 ✓（C4 —— Memory 方案 §6 ✓）。

⚠️ **只置 ``retired``** ✓（不物理删 ✓ —— 保留审计 ✓ —— §6 ✓）——
⚠️ **向量同步删** ✓（不留残留副本 ✓ —— §5.4 ✓）。
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from qzdap.modules.memory.application.ports import (
    MemoryCatalogRepository,
    VectorSearchPort,
)
from qzdap_agent_runtime.memory.eviction import (
    EvictionCandidate,
    EvictionPort,
)


class SqlEvictionStore(EvictionPort):
    """**淘汰**的存取 ✓。"""

    def __init__(
        self,
        catalog: MemoryCatalogRepository,
        *,
        vectors: VectorSearchPort | None = None,
    ) -> None:
        self._catalog = catalog
        self._vectors = vectors

    async def list_candidates(self, *, workspace_id: UUID, layer: str) -> list[EvictionCandidate]:
        """**活着的条目** ✓（只有 L2 有淘汰策略 ✓ —— L3 已退役 ✓）。"""
        if layer != "l2":
            return []
        facts = await self._catalog.list_l2(workspace_id)
        return [
            EvictionCandidate(
                id=fact.id,
                content_bytes=len((fact.value or "").encode("utf-8")),
                updated_at=fact.updated_at,
                last_used_at=fact.last_used_at,
                used_count=int(fact.used_count or 0),
            )
            for fact in facts
            if str(fact.status) == "confirmed"
        ]

    async def retire(self, *, workspace_id: UUID, item_ids: tuple[UUID, ...]) -> None:
        """**置 retired** ✓（不物理删 ✓ —— 审计留痕 ✓）。"""
        now = datetime.now(UTC)
        for item_id in item_ids:
            fact = await self._catalog.get_l2(item_id)
            if fact is None or fact.workspace_id != workspace_id:
                continue
            fact.status = "retired"  # type: ignore[assignment]
            fact.updated_at = now
            await self._catalog.update_l2(fact)

    async def delete_vectors(self, item_ids: tuple[UUID, ...]) -> None:
        """**同步删向量** ✓。"""
        if self._vectors is None or not item_ids:
            return
        await self._vectors.delete(item_ids)


__all__ = ["SqlEvictionStore"]
