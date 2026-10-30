"""Adapter wiring the memory catalog into agent_runtime's MemoryPort."""

from __future__ import annotations

from uuid import UUID

from qzdap.modules.memory.application.services import MemoryRuntimeService


class MemoryServiceAdapter:
    """Adapts ``MemoryRuntimeService.recall`` → ``MemoryPort.recall`` ✓。

    ⚠️ **只接运行面** ✓ —— 管理面在 ``MemoryAdminService`` ✓（平面分离 ✓）。
    """

    def __init__(self, memory_service: MemoryRuntimeService) -> None:
        self._service = memory_service

    async def recall(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        query: str,
        top_k: int,
        user_id: UUID | None = None,
    ) -> list[dict]:
        """召回 → **dict 形状** ✓（调用方要 dict ✓）。

        ⚠️ 生产侧现在返回 ``RecallHit`` ✓（Memory Stage 0 · M-04 ✓）—— 形状
        的转换**只在这一处** ✓（转换规则只有一份 ✓）。
        """
        hits = await self._service.recall(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            query=query,
            top_k=top_k,
            user_id=user_id,
        )
        return [
            {
                "id": hit.source_id,
                # ⚠️ **ref_id / version** ✓ —— Context 的 manifest 组装要靠
                # 它们才能说清「这条记忆是哪一条、哪个版本」✓。
                "ref_id": hit.ref_id,
                "version": hit.version,
                "content": hit.content,
                "score": hit.score,
                "scope": hit.scope,
                "layer": hit.layer,
                "used_count": hit.used_count,
            }
            for hit in hits
        ]

    async def write(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        owner_id: UUID,
        content: str,
        metadata: dict | None = None,
    ) -> dict:
        return await self._service.write(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            owner_id=owner_id,
            content=content,
            metadata=metadata,
        )


__all__ = ["MemoryServiceAdapter"]
