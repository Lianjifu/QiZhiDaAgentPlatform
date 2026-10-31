"""候选端口的**模块侧实现** ✓ —— 把仓储 / 向量库包装成契约层的候选 ✓。

依据：Memory 方案 §3.1（候选检索 ✓）、§3.3（向量优先 ✓）、§3.5（provenance ✓）。

⚠️ **两个候选源分成两个类** ✓ —— 不是因为洁癖 ✓：契约层的两个端口**同名
``search``** ✓，一个类没法同时实现两种行为 ✗✗。

⚠️ **词法候选下推到 SQL** ✓（``ILIKE`` ✓）—— Python 侧逐行过滤是**现状的
缺陷** ✗（全量加载 ✗ → 延迟随 N 线性增长 ✗）。
"""

from __future__ import annotations

from uuid import UUID

from qzdap.modules.memory.application.ports import (
    EmbeddingPort,
    MemoryCatalogRepository,
    VectorSearchPort,
)
from qzdap.modules.memory.domain.entities import L2Fact
from qzdap_agent_runtime.memory.retrieval import Candidate


def keyword_score(needle: str, hay: str) -> float:
    """词法打分 ✓（0.05 – 1.0 ✓）—— 与旧路径**同口径** ✓。

    ⚠️ **命中越全分越高** ✓ —— 全部词命中 → 1.0 ✓；部分命中 → 按比例 ✓。
    """
    if not needle:
        return 0.1
    if needle in hay:
        return 1.0
    parts = [part for part in needle.split() if part]
    if not parts:
        return 0.05
    hits = sum(1 for part in parts if part in hay)
    return 0.15 + 0.85 * (hits / len(parts)) if hits else 0.05


def _l2_candidate(fact: L2Fact, score: float) -> Candidate:
    """L2 行 → 候选 ✓（provenance 齐全 ✓ —— §3.5 ✓）。"""
    return Candidate(
        ref_id=str(fact.id),
        layer="l2",
        content=fact.recall_text(),
        score=score,
        scope="user",
        used_count=int(fact.used_count or 0),
        version=str(fact.version or 1),
        content_hash=str(fact.content_hash or ""),
        created_at=fact.created_at.isoformat() if fact.created_at else "",
    )


class LexicalCandidateAdapter:
    """词法候选 ✓ —— **过滤与截断在 SQL 里** ✓。"""

    def __init__(self, catalog: MemoryCatalogRepository) -> None:
        self._catalog = catalog

    async def search(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        user_id: UUID | None,
        query: str,
        limit: int,
        session_id: UUID | None = None,
    ) -> list[Candidate]:
        _ = tenant_id  # 租户过滤由 ORM 的租户作用域承担 ✓
        needle = query.strip().lower()
        if not needle:
            return []
        facts = await self._catalog.search_l2_by_keyword(
            workspace_id,
            user_id=user_id,
            keyword=needle,
            limit=limit,
            session_id=session_id,
        )
        # ⚠️ **不再查 L3** ✓ —— L3 退役 ✓（决策 #1 ✓ —— M-47 ✓）→
        # 团队知识走 **knowledge** 的检索 ✓（不再双份注入 ✗✗ —— 台账 X15 ✓）。
        candidates = [
            _l2_candidate(fact, keyword_score(needle, fact.recall_text().lower())) for fact in facts
        ]
        candidates.sort(key=lambda item: item.score, reverse=True)
        return candidates[:limit]


class VectorCandidateAdapter:
    """向量候选 ✓ —— **查询向量在这里生成** ✓（契约层不碰 embedding ✓）。

    ⚠️ **embedding / 向量库不可用 → 抛异常** ✓ —— 由流水线**降级**成纯词法
    ✓（C10 ✓ —— 这里**不吞异常** ✗✗，吞了就没人知道降级了 ✗）。
    """

    def __init__(
        self,
        *,
        embedding: EmbeddingPort | None,
        vectors: VectorSearchPort | None,
    ) -> None:
        self._embedding = embedding
        self._vectors = vectors

    async def search(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        user_id: UUID | None,
        query: str,
        limit: int,
        session_id: UUID | None = None,
    ) -> list[Candidate]:
        if self._embedding is None or self._vectors is None:
            raise RuntimeError("vector search is not available")
        [query_vec] = await self._embedding.embed([query.strip()])
        hits = await self._vectors.search(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            query_embedding=query_vec,
            top_k=limit,
            user_id=user_id,
            session_id=session_id,
        )
        return [
            Candidate(
                ref_id=str(hit.item_id),
                layer=hit.layer,
                content=hit.content,
                score=float(hit.score),
                scope="user",
            )
            for hit in hits
        ]


class PinnedCandidateAdapter:
    """**显式绑定**的条目 ✓（§7.1 ✓）—— 按 id 取 ✓（不靠搜索 ✓）。

    ⚠️ **用户过滤照旧** ✓ —— 绑定的是「这个用户的记忆」✓ —— 别人的记忆
    绑过来也看不见 ✓（**不串号** ✓ —— 决策 #11 ✓）。
    """

    def __init__(self, catalog: MemoryCatalogRepository) -> None:
        self._catalog = catalog

    async def get_by_ids(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        user_id: UUID | None,
        ids: tuple[str, ...],
    ) -> list[Candidate]:
        _ = (tenant_id, workspace_id)
        candidates: list[Candidate] = []
        for raw_id in ids:
            try:
                item_id = UUID(str(raw_id))
            except (TypeError, ValueError):
                continue
            fact = await self._catalog.get_l2(item_id)
            if fact is not None:
                if user_id is not None and fact.user_id != user_id:
                    continue
                candidates.append(_l2_candidate(fact, 1.0))
        return candidates


__all__ = [
    "LexicalCandidateAdapter",
    "PinnedCandidateAdapter",
    "VectorCandidateAdapter",
    "keyword_score",
]
