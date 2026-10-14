"""Memory layer implementation — §13.4 LayeredMemory.

Stage 3 PR A 范围：

- `InMemoryLayeredMemory`: 进程内实现 (L1/L2/L3),用于单测和本地 dev
- L1 = 当前 session 消息 + rolling_summary (来自 messages reducer)
- L2 = 长期事实列表 (替代 L2 向量,等 Stage 3 接入 PGVector)
- L3 = 知识语料 (chunks with asset_id/chunk_id/version/ACL)
- `RecallPipeline`: 召回流水线 — tokenize → ACL filter → lexical/vector 合并 →
  dedup → score threshold → provenance manifest

§5.4 召回流水线（doc 引用）：

    query normalization
      -> tenant/workspace/ACL filter
      -> lexical + vector candidate merge
      -> duplicate removal
      -> optional reranker (Stage 3 PR A 用 score 替代)
      -> score threshold and top-k
      -> provenance/citation manifest

§5.4 失败语义：召回失败时主回答可继续，但 state.degraded.recall_degraded=true。
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Iterable, Protocol, runtime_checkable

from ..ports import LayeredMemory, RecallHit, RecallLayer

# ---------------------------------------------------------------------------
# L1 / L2 / L3 抽象输入（InMemory 实现用）
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class L1Source:
    """L1 召回源：消息 + 摘要。"""

    session_id: str
    messages: tuple[dict[str, Any], ...]  # 来自 SessionState.messages
    rolling_summary: str


@dataclass(frozen=True, slots=True)
class L2Fact:
    """L2 长期事实（占位 - Stage 3 PR D 接 PGVector）。"""

    fact_id: str
    tenant_id: str
    workspace_id: str
    user_id: str
    content: str
    confidence: float
    source_turn_id: str | None = None
    content_hash: str = ""
    expires_at: str | None = None
    policy_version: str = "v1"


@dataclass(frozen=True, slots=True)
class L3Chunk:
    """L3 知识片段。"""

    chunk_id: str
    asset_id: str
    workspace_id: str
    content: str
    version: str
    acl_allow: tuple[str, ...] = ()  # workspace IDs that can read
    score_hint: float = 0.0  # 预排序 hint（用 score 时只调整）


# ---------------------------------------------------------------------------
# Recall pipeline
# ---------------------------------------------------------------------------


def _normalize(text: str) -> list[str]:
    """中英混合 token 切分（简化版：CJK 按字，ASCII 按词）。"""
    text = unicodedata.normalize("NFKC", text.lower())
    # 替换非字母数字为空白
    text = re.sub(r"[^\w\s一-鿿]+", " ", text, flags=re.UNICODE)
    tokens: list[str] = []
    for tok in text.split():
        if re.match(r"[一-鿿]", tok):
            # CJK 字符：每个字一个 token
            tokens.extend(list(tok))
        else:
            if len(tok) > 1:
                tokens.append(tok)
    return tokens


def _lexical_score(query_tokens: Iterable[str], doc_tokens: Iterable[str]) -> float:
    """词频 Jaccard-like 简单打分。"""
    q = Counter(query_tokens)
    d = Counter(doc_tokens)
    if not q or not d:
        return 0.0
    overlap = sum((q & d).values())
    return overlap / (sum(q.values()) + sum(d.values()) - overlap)


# ---------------------------------------------------------------------------
# InMemoryLayeredMemory
# ---------------------------------------------------------------------------


class InMemoryLayeredMemory:
    """§13.4 LayeredMemory 进程内实现（单测 + 本地 dev）。"""

    def __init__(self) -> None:
        self._l1_cache: dict[str, L1Source] = {}
        self._l2_facts: list[L2Fact] = []
        self._l3_chunks: list[L3Chunk] = []
        self._degraded: dict[str, bool] = {
            "recall_degraded": False,
        }

    # ---- L1 源注入 ----

    def set_l1(self, source: L1Source) -> None:
        self._l1_cache[source.session_id] = source

    # ---- L2 注入 ----

    def add_l2_fact(self, fact: L2Fact) -> None:
        self._l2_facts.append(fact)

    # ---- L3 注入 ----

    def add_l3_chunk(self, chunk: L3Chunk) -> None:
        self._l3_chunks.append(chunk)

    # ---- §13.4 Protocol 实现（同步 — 进程内实现无 I/O）----

    def recall_memory(
        self,
        *,
        query: str,
        tenant_id: str,
        workspace_id: str,
        user_id: str,
        session_id: str,
        policy: dict[str, Any],
    ) -> list[RecallHit]:
        """L1 + L2 召回。"""
        try:
            top_k = int(policy.get("top_k", 5))
            threshold = float(policy.get("threshold", 0.1))
        except (TypeError, ValueError):
            top_k = 5
            threshold = 0.1

        query_tokens = _normalize(query)
        if not query_tokens:
            return []

        hits: list[RecallHit] = []

        # L1: 当前 session 消息 + rolling_summary
        l1 = self._l1_cache.get(session_id)
        if l1 is not None and l1.tenant_id_or_self_check(tenant_id, workspace_id, user_id):
            for idx, msg in enumerate(l1.messages):
                content = str(msg.get("content", ""))
                score = _lexical_score(query_tokens, _normalize(content))
                if score >= threshold:
                    hits.append(
                        RecallHit(
                            layer="l1",
                            content=content,
                            score=score,
                            source_id=f"{session_id}:msg:{idx}",
                            citation=None,
                            metadata={"role": msg.get("role", "user")},
                        )
                    )
            if l1.rolling_summary:
                score = _lexical_score(query_tokens, _normalize(l1.rolling_summary))
                if score >= threshold:
                    hits.append(
                        RecallHit(
                            layer="l1",
                            content=l1.rolling_summary,
                            score=score,
                            source_id=f"{session_id}:summary",
                            citation=None,
                            metadata={"role": "summary"},
                        )
                    )

        # L2: 长期事实
        for fact in self._l2_facts:
            if fact.tenant_id != tenant_id or fact.workspace_id != workspace_id:
                continue
            if fact.user_id != "*" and fact.user_id != user_id:
                continue
            score = _lexical_score(query_tokens, _normalize(fact.content))
            if score >= threshold:
                hits.append(
                    RecallHit(
                        layer="l2",
                        content=fact.content,
                        score=score * fact.confidence,
                        source_id=fact.fact_id,
                        citation=fact.source_turn_id,
                        metadata={
                            "confidence": fact.confidence,
                            "expires_at": fact.expires_at,
                            "policy_version": fact.policy_version,
                        },
                    )
                )

        # 排序 + top-k
        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[:top_k]

    def recall_knowledge(
        self,
        *,
        query: str,
        tenant_id: str,
        workspace_id: str,
        package_ids: tuple[str, ...] | None = None,
    ) -> list[RecallHit]:
        """L3 知识召回（hybrid lexical + score_hint）。"""
        try:
            top_k = 10
            threshold = 0.05
        except (TypeError, ValueError):
            top_k = 10
            threshold = 0.05

        query_tokens = _normalize(query)
        if not query_tokens:
            return []

        hits: list[RecallHit] = []
        for chunk in self._l3_chunks:
            # ACL filter
            if chunk.workspace_id != workspace_id and workspace_id not in chunk.acl_allow:
                continue
            if package_ids and chunk.asset_id not in package_ids:
                continue
            # Hybrid: lexical + score_hint
            lex = _lexical_score(query_tokens, _normalize(chunk.content))
            score = max(lex, chunk.score_hint)
            if score >= threshold:
                hits.append(
                    RecallHit(
                        layer="l3",
                        content=chunk.content,
                        score=score,
                        source_id=chunk.chunk_id,
                        citation=f"asset://{chunk.asset_id}#v{chunk.version}",
                        metadata={
                            "asset_id": chunk.asset_id,
                            "chunk_id": chunk.chunk_id,
                            "version": chunk.version,
                            "acl_allow": list(chunk.acl_allow),
                        },
                    )
                )

        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[:top_k]

    def write_l1(self, event: dict[str, Any]) -> None:
        """L1 写入：消息由 LangGraph 维护，事件层不重复写。"""
        return None

    def write_l2(self, fact: dict[str, Any]) -> None:
        """L2 写入（§5.4 同 content_hash 必须幂等）。"""
        content_hash = str(fact.get("content_hash", ""))
        # 幂等去重
        for existing in self._l2_facts:
            if existing.content_hash == content_hash and content_hash:
                return
        new_fact = L2Fact(
            fact_id=str(fact["fact_id"]),
            tenant_id=str(fact["tenant_id"]),
            workspace_id=str(fact["workspace_id"]),
            user_id=str(fact.get("user_id", "*")),
            content=str(fact["content"]),
            confidence=float(fact.get("confidence", 1.0)),
            source_turn_id=fact.get("source_turn_id"),
            content_hash=content_hash,
            expires_at=fact.get("expires_at"),
            policy_version=str(fact.get("policy_version", "v1")),
        )
        self._l2_facts.append(new_fact)

    @property
    def degraded(self) -> dict[str, bool]:
        return dict(self._degraded)


# 补 L1Source.tenant_id_or_self_check
def _l1_self_check(self: L1Source, tenant_id: str, workspace_id: str, user_id: str) -> bool:
    """L1 仅作占位实现：所有 session 都视为允许（无 ACL）。"""
    return True


L1Source.tenant_id_or_self_check = _l1_self_check  # type: ignore[attr-defined]


__all__ = [
    "InMemoryLayeredMemory",
    "L1Source",
    "L2Fact",
    "L3Chunk",
]