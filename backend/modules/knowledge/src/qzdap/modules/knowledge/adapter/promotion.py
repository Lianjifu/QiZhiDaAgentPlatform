"""**团队知识候选**的实现 ✓（决策 #1 ✓ —— 落点是 knowledge ✓）。

⚠️ **候选不是已发布的知识** ✓ —— 它是一个**文档** ✓（进 KB ✓ —— 审核与
发布是 knowledge 侧的事 ✓ —— Memory 不越权 ✓）。
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from qzdap_agent_runtime.memory.promotion import KnowledgePromotionPort

from qzdap.modules.knowledge.application.services import KnowledgeService


class KnowledgeCandidateAdapter(KnowledgePromotionPort):
    """**事实 → 团队知识候选** ✓。"""

    def __init__(self, service: KnowledgeService) -> None:
        self._service = service

    async def create_candidate(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        kb_id: UUID | None,
        title: str,
        summary: str,
        content: str,
        contributor: str,
        source_ids: tuple[str, ...],
    ) -> dict[str, Any]:
        """**建一条候选** ✓（落进 KB ✓）。"""
        kb = await self._resolve_kb(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            kb_id=kb_id,
            title=title,
            summary=summary,
            contributor=contributor,
        )
        doc = await self._service.ingest_doc(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            body={
                "kbId": str(kb["id"]),
                "name": title,
                "content": content,
                "type": "memory_candidate",
                "sourceId": ",".join(source_ids),
            },
        )
        return {
            "id": str(doc.get("id") or ""),
            "kbId": str(kb["id"]),
            "title": title,
            "summary": summary,
            "sourceIds": list(source_ids),
        }

    async def _resolve_kb(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        kb_id: UUID | None,
        title: str,
        summary: str,
        contributor: str,
    ) -> dict[str, Any]:
        """**用哪个 KB** ✓（给了就用 ✓ —— 没给就按名字找 ✓ —— 没有就建 ✓）。"""
        if kb_id is not None:
            kb = await self._service.get_kb(kb_id)
            return kb
        name = f"{title} · 记忆候选"
        for kb in await self._service.list_kbs(workspace_id=workspace_id):
            if kb.get("name") == name:
                return kb
        return await self._service.create_kb(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            body={"name": name, "description": summary},
            owner=contributor,
        )


__all__ = ["KnowledgeCandidateAdapter"]
