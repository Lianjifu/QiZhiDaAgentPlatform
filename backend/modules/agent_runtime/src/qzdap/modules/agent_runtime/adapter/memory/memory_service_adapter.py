"""Adapter wiring the memory catalog into agent_runtime's MemoryPort."""

from __future__ import annotations

from uuid import UUID

from qzdap.modules.memory.application.services import MemoryRuntimeService
from qzdap_agent_runtime.memory.policy import MemoryPolicy


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
        session_id: UUID | None = None,
        policy: MemoryPolicy | None = None,
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
            session_id=session_id,
            policy=policy,
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

    async def write_turn(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        user_id: UUID,
        session_id: UUID,
        turn_id: UUID | None = None,
        user_input: str,
        assistant_reply: str = "",
        policy: MemoryPolicy | None = None,
    ) -> dict:
        """**新 Writer** ✓ —— 走契约层的五步流水线 ✓（Memory Stage 3 ✓）。

        ⚠️ **策略绑定在这一步生效** ✓（§7.1 ✓）—— ``enabled=False`` →
        **一条都不写** ✓（``written=0`` + ``skipped`` ✓ —— 调用方能知道原因 ✓）。
        """
        outcome = await self._service.write_turn(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            user_id=user_id,
            session_id=session_id,
            turn_id=turn_id,
            user_input=user_input,
            assistant_reply=assistant_reply,
            policy=policy,
        )
        return {
            "written": len(outcome.written),
            "rejected": len(outcome.rejected),
            "deduplicated": len(outcome.deduplicated),
            # ⚠️ **跳过原因要看得见** ✓（否则「agent 关了记忆」没人知道 ✗✗）。
            "skipped": outcome.skipped,
            # ⚠️ **绑定的保留策略标签** ✓（§7.1 ✓ —— 绑定要看得见 ✓）。
            "retention_label": outcome.retention_label,
        }


__all__ = ["MemoryServiceAdapter"]
