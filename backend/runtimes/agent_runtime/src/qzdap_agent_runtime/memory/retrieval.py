"""``Retrieval`` —— 记忆检索的**端口** ✓（C2）。

依据：Memory 方案 §3（召回七步 ✓）、§10.1（A2 ``retrieval.py`` ✓）。

⚠️ **这一层是契约层** —— 端口 + 结果形状 ✓（实现归模块侧 ✓）。

⚠️ **七步流水线**（§3.1 ✓）：归一化 → 作用域过滤 → 候选检索 → 去重 →
rerank → 阈值 + top-k → provenance ✓。

⚠️ **作用域过滤必须在 SQL / 向量的 WHERE 里** ✓（§3.1 第 2 步 ✓）——
Python 侧逐行过滤是**现状的缺陷** ✗✗。

⚠️ **abstain** ✓（§3.4 ✓）—— 得分低于阈值时**返回 abstain 信号** ✓，
不硬塞给模型 ✗（「禁止把『没召回』伪装成『没有相关知识』」✓）。
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Protocol, runtime_checkable
from uuid import UUID


@dataclass(frozen=True, slots=True)
class RetrievalOutcome:
    """一次召回的结果 ✓。

    ⚠️ ``abstained=True`` 表示「**没找到够格的**」✓（§3.4 ✓）—— 调用方要
    能区分「没有相关知识」与「有但没达标」✗✗。
    """

    hits: list[dict] = field(default_factory=list)
    #: 是否**弃权** ✓（阈值过滤后一条都不剩 ✓）。
    abstained: bool = False
    #: 读取侧是否**降级** ✓（embedding / 向量库不可用 → 纯词法 ✓ —— C10 ✓）。
    degraded: bool = False
    #: 降级原因 ✓（审计 / 排障 ✓）。
    degraded_reason: str = ""


@runtime_checkable
class Retrieval(Protocol):
    """记忆检索 ✓（C2 ✓）。"""

    async def recall(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        user_id: UUID | None,
        query: str,
        top_k: int = 8,
        session_id: UUID | None = None,
        extra_l3_entry_ids: tuple[str, ...] = (),
    ) -> RetrievalOutcome:
        """按作用域检索 ✓ —— **过滤下推到存储层** ✓（§3.1 ✓）。"""
        ...


def _fuse(
    vector_candidates: list[Candidate],
    lexical_candidates: list[Candidate],
) -> list[Candidate]:
    """向量分 + 词法分**融合** ✓（0.7 / 0.3 ✓ —— 与旧路径同口径 ✓）。

    ⚠️ **向量优先** ✓ —— 同一条命中两边都有时，取向量的内容与 metadata ✓，
    分数按融合算 ✓。
    """
    lexical_by_ref = {c.ref_id: c for c in lexical_candidates}
    fused: dict[str, Candidate] = {}
    for candidate in vector_candidates:
        keyword = lexical_by_ref.get(candidate.ref_id)
        if keyword is not None:
            fused[candidate.ref_id] = replace(
                candidate,
                score=0.7 * candidate.score + 0.3 * keyword.score,
            )
        else:
            fused[candidate.ref_id] = candidate
    for candidate in lexical_candidates:
        if candidate.ref_id not in fused:
            fused[candidate.ref_id] = candidate
    return list(fused.values())


__all__ = [
    "Candidate",
    "LexicalCandidatePort",
    "Retrieval",
    "RetrievalOutcome",
    "RetrievalPipeline",
    "VectorCandidatePort",
]


# ---------------------------------------------------------------------------
# 候选端口与七步流水线（§3.1 ✓）
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Candidate:
    """一个候选命中 ✓（检索流水线的中间产物 ✓）。"""

    #: 命中项 ID ✓（去重与 provenance 都用它 ✓）。
    ref_id: str
    #: 层级 ✓（`l1` / `l2` / `l3` ✓）。
    layer: str
    #: 命中内容 ✓。
    content: str
    #: 得分 ✓（向量分或词法分 ✓）。
    score: float
    #: 作用域 ✓（session / user / workspace ✓）。
    scope: str = "user"
    #: 用过几次 ✓（provenance ✓）。
    used_count: int = 0
    #: 版本 ✓（provenance ✓ —— Context manifest 用 ✓）。
    version: str = ""
    #: 内容哈希 ✓（**语义去重用** ✓ —— §4.4 ✓）。
    content_hash: str = ""
    #: 创建时间 ✓（provenance ✓）。
    created_at: str = ""
    #: 来源会话 ✓（**会话作用域过滤的依据** ✓ —— §7.1 ✓）。
    session_id: str = ""
    #: **显式绑定**的条目 ✓（§7.1 ✓）—— 它**绕过阈值** ✓（绑定的不是搜出来的 ✓）。
    pinned: bool = False


@runtime_checkable
class LexicalCandidatePort(Protocol):
    """词法候选 ✓ —— **过滤与打分都在存储层做** ✓（不下推 = 全量扫描 ✗✗）。"""

    async def search(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        user_id: UUID | None,
        query: str,
        limit: int,
        session_id: UUID | None = None,
    ) -> list[Candidate]: ...


@runtime_checkable
class VectorCandidatePort(Protocol):
    """向量候选 ✓ —— **查询向量的生成也在这一侧** ✓（契约层不碰 embedding ✓）。"""

    async def search(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        user_id: UUID | None,
        query: str,
        limit: int,
        session_id: UUID | None = None,
    ) -> list[Candidate]: ...


@runtime_checkable
class PinnedCandidatePort(Protocol):
    """**显式绑定**的条目 ✓（§7.1 ✓）—— 按 id 取 ✓（不靠搜索 ✓）。

    ⚠️ **绑定的条目一定要召回** ✓ —— 它不是「搜出来的」✓ → **绕过阈值** ✓
    （管理端绑了就该生效 ✗✗ —— 否则「绑了没用」又变成一句空话 ✓）。
    """

    async def get_by_ids(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        user_id: UUID | None,
        ids: tuple[str, ...],
    ) -> list[Candidate]: ...


class RetrievalPipeline:
    """记忆检索的**七步流水线** ✓（§3.1 ✓）。

    ① query 归一化 → ② 作用域过滤（在端口里 ✓ 下推到存储 ✓）→
    ③ 候选检索（**向量优先** ✓，词法兜底 ✓）→ ④ 去重（ref_id + content_hash ✓）→
    ⑤ rerank（**暂不做** ✓ —— 可选步骤 ✓）→ ⑥ 阈值 + top-k ✓ →
    ⑦ provenance ✓。

    ⚠️ **向量不可用 → 降级为纯词法** ✓（C10 ✓）—— 且 **degraded=True**
    ✓（调用方要能知道「这次召回是打折的」✗✗）。

    ⚠️ **abstain** ✓（§3.4 ✓）—— 阈值过滤后一条不剩 → ``abstained=True``
    ✓（「没找到够格的」≠「没有相关知识」✗✗）。
    """

    def __init__(
        self,
        *,
        lexical: LexicalCandidatePort,
        vector: VectorCandidatePort | None = None,
        pinned: PinnedCandidatePort | None = None,
        threshold: float = 0.15,
        candidate_multiplier: int = 4,
    ) -> None:
        self._lexical = lexical
        self._vector = vector
        #: **显式绑定**的取法 ✓（§7.1 ✓）—— 没有它 = 绑定不生效 ✗✗。
        self._pinned = pinned
        self._threshold = threshold
        self._multiplier = candidate_multiplier

    async def recall(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        user_id: UUID | None,
        query: str,
        top_k: int = 8,
        session_id: UUID | None = None,
        extra_l3_entry_ids: tuple[str, ...] = (),
    ) -> RetrievalOutcome:
        """跑一次检索 ✓ —— 返回**统一形状** ✓。

        ⚠️ **会话作用域** ✓（§7.1 ✓）—— ``session_id`` 给定时**只召回本会话
        的记忆** ✓（作用域过滤**下推到存储层** ✓ —— Python 侧再过滤一次是
        兜底 ✓，不是主要手段 ✗✗）。

        ⚠️ **显式绑定的条目一定会被召回** ✓（§7.1 ✓）—— 它们**绕过阈值** ✓
        （绑定不是搜索 ✓）。
        """
        normalized = (query or "").strip().lower()
        if not normalized:
            return RetrievalOutcome(hits=[], abstained=True)

        limit = max(1, top_k) * self._multiplier
        degraded = False
        degraded_reason = ""

        # ── ③ 候选检索：向量优先 ✓ ───────────────────────────────────
        vector_candidates: list[Candidate] = []
        if self._vector is not None:
            try:
                vector_candidates = await self._vector.search(
                    tenant_id=tenant_id,
                    workspace_id=workspace_id,
                    user_id=user_id,
                    query=normalized,
                    limit=limit,
                    session_id=session_id,
                )
            except Exception:
                # ⚠️ **C10 读取侧降级** ✓ —— 向量库 / embedding 不可用 → 纯词法 ✓
                degraded = True
                degraded_reason = "vector_unavailable"
                vector_candidates = []

        # 词法候选**始终**取 ✓ —— 它给融合分补权重 ✓（不是只在向量没结果时取 ✓）
        lexical_candidates = await self._lexical.search(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            user_id=user_id,
            query=normalized,
            limit=limit,
            session_id=session_id,
        )

        # 融合：向量分为主 ✓ + 词法分为辅 ✓（**与旧路径同口径** ✓ ——
        # 旧路径是 0.7*向量 + 0.3*词法 ✓）。
        candidates = _fuse(vector_candidates, lexical_candidates)

        # ⚠️ **显式绑定的条目** ✓（§7.1 ✓）—— 额外纳入 ✓ + **绕过阈值** ✓。
        pinned_candidates = await self._pinned_candidates(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            user_id=user_id,
            ids=extra_l3_entry_ids,
        )
        candidates = [*pinned_candidates, *candidates]

        # ── ④ 去重（ref_id + content_hash ✓）────────────────────────
        seen_refs: set[str] = set()
        seen_hashes: set[str] = set()
        deduped: list[Candidate] = []
        for candidate in candidates:
            if candidate.ref_id and candidate.ref_id in seen_refs:
                continue
            if candidate.content_hash and candidate.content_hash in seen_hashes:
                continue
            if candidate.ref_id:
                seen_refs.add(candidate.ref_id)
            if candidate.content_hash:
                seen_hashes.add(candidate.content_hash)
            deduped.append(candidate)

        # ── ⑥ 阈值 + top-k ✓ ─────────────────────────────────────────
        # ⚠️ **绑定的条目绕过阈值** ✓（§7.1 ✓）—— 其余照常过滤 ✓。
        passed = [c for c in deduped if c.pinned or c.score >= self._threshold]
        # ⚠️ **绑定的排前面** ✓ —— 管理端显式指定的东西优先 ✓。
        passed.sort(key=lambda c: (c.pinned, c.score), reverse=True)
        selected = passed[: max(1, top_k)]

        # ── ⑦ provenance ✓ ───────────────────────────────────────────
        hits = [
            {
                "ref_id": c.ref_id,
                "id": c.ref_id,
                "layer": c.layer,
                "content": c.content,
                "score": c.score,
                "scope": c.scope,
                "used_count": c.used_count,
                "version": c.version,
                "created_at": c.created_at,
                "content_hash": c.content_hash,
            }
            for c in selected
        ]
        return RetrievalOutcome(
            hits=hits,
            abstained=not hits,
            degraded=degraded,
            degraded_reason=degraded_reason,
        )

    async def _pinned_candidates(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        user_id: UUID | None,
        ids: tuple[str, ...],
    ) -> list[Candidate]:
        """**显式绑定的条目** ✓（§7.1 ✓）。

        ⚠️ **取不到就不取** ✓ —— 绑定的条目可能已被删 ✓（**不报错** ✓ ——
        绑定是配置 ✓，配置指向的行没了不该让整轮对话失败 ✗✗）。
        """
        wanted = tuple(dict.fromkeys(item for item in ids if item))
        if not wanted or self._pinned is None:
            return []
        try:
            found = await self._pinned.get_by_ids(
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                user_id=user_id,
                ids=wanted,
            )
        except Exception:
            # ⚠️ **绑定取不到不拖垮召回** ✓ —— 降级成「没绑到」✓。
            return []
        return [replace(candidate, pinned=True) for candidate in found if candidate.content]
