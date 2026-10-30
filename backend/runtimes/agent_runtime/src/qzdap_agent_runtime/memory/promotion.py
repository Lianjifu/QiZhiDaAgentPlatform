"""**团队知识候选**的落点 ✓（决策 #1 ✓ —— L3 退役 ✓）。

⚠️ **Memory 不直接 import knowledge 模块** ✓ → 走窄端口 ✓（契约层 ✓）。

⚠️ **候选不是已发布的知识** ✓ —— 要人工审核 ✓（决策 #1 ✓ —— 「事实 → 团队
知识候选」✓ —— 落点是 knowledge 模块的 KB ✓）。
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable
from uuid import UUID


@runtime_checkable
class KnowledgePromotionPort(Protocol):
    """**团队知识候选**的落点 ✓（决策 #1 ✓ —— L3 退役 ✓）。

    ⚠️ **实现在 knowledge 那一侧** ✓（它拥有 KB ✓）—— Memory 只管调用 ✓。
    """

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
        """**建一条候选** ✓ —— 返回候选的描述 ✓（id / 标题 ✓）。"""
        ...


__all__ = ["KnowledgePromotionPort"]
