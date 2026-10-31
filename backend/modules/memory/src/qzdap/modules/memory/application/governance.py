"""**记忆域的数据主体 scope** ✓（C9 ✓ —— 决策 #8 ✓）。

⚠️ **治理域只认 scope** ✓ —— 它**不认识**记忆表 ✗✗ → 记忆域自己实现一个
scope ✓（``scope = "memory"`` ✓），治理域按名字调它 ✓（边界 ✓）。

⚠️ **删要删干净** ✓：
- **L2 行** ✓（用户级事实 ✓）；
- **向量行** ✓（否则向量成了**残留副本** ✗✗ —— §7.4 的原话 ✓）；
- **会话缓冲** ✓（那也是那个人的内容 ✓ —— L1 表退役后的落点 ✓）。

⚠️ **导出要给全量** ✓ —— L2 的内容 + 来源 ✓（用户拿回自己的数据 ✓）。
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from qzdap.modules.memory.application.ports import (
    MemoryCatalogRepository,
    VectorSearchPort,
)
from qzdap_agent_runtime.governance.data_subject import DataSubjectRequest
from qzdap_agent_runtime.memory.refine import BufferPort


class MemoryDataSubjectScope:
    """**记忆域**的删除 / 导出 ✓。"""

    scope = "memory"

    def __init__(
        self,
        *,
        catalog: MemoryCatalogRepository,
        vectors: VectorSearchPort | None = None,
        buffer: BufferPort | None = None,
    ) -> None:
        self._catalog = catalog
        self._vectors = vectors
        self._buffer = buffer

    async def delete(self, request: DataSubjectRequest) -> dict[str, Any]:
        """**删掉这个用户的记忆** ✓（L2 + 向量 + 缓冲 ✓）。"""
        workspace_id = self._require_workspace(request)
        facts = await self._catalog.list_l2(workspace_id, user_id=request.user_id)
        ids = [fact.id for fact in facts]
        deleted = await self._catalog.delete_l2(ids)
        # ⚠️ **向量要同步删** ✓ —— 不删就是**残留副本** ✗✗（§7.4 ✓）。
        vectors_deleted = 0
        if self._vectors is not None and ids:
            await self._vectors.delete(ids)
            vectors_deleted = len(ids)
        buffers_deleted = 0
        if self._buffer is not None:
            buffers_deleted = await self._buffer.delete_user(
                workspace_id=workspace_id, user_id=request.user_id
            )
        return {
            "facts": deleted,
            "vectors": vectors_deleted,
            "buffers": buffers_deleted,
        }

    async def export(self, request: DataSubjectRequest) -> dict[str, Any]:
        """**导出这个用户的记忆** ✓（L2 的内容与来源 ✓）。"""
        workspace_id = self._require_workspace(request)
        facts = await self._catalog.list_l2(workspace_id, user_id=request.user_id)
        return {
            "facts": [
                {
                    "id": str(fact.id),
                    "key": fact.key,
                    "value": fact.value,
                    "category": fact.category,
                    "confidence": fact.confidence,
                    "status": fact.status,
                    "createdAt": fact.created_at.isoformat() if fact.created_at else "",
                    "updatedAt": fact.updated_at.isoformat() if fact.updated_at else "",
                    "sourceSession": fact.source_session,
                    "contentHash": fact.content_hash,
                }
                for fact in facts
            ],
        }

    @staticmethod
    def _require_workspace(request: DataSubjectRequest) -> UUID:
        """**记忆是工作区级的** ✓ —— 缺工作区**明确失败** ✓（不猜 ✓）。"""
        if request.workspace_id is None:
            raise ValueError("memory scope requires workspace_id")
        return request.workspace_id


__all__ = ["MemoryDataSubjectScope"]
