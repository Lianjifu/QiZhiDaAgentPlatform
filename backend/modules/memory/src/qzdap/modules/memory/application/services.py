"""平面 A · 记忆**运行面**的服务 —— 召回 + 自动沉淀 ✓。

依据：Memory 方案 §10.1（平面 A）、§2.2 规则 6（平面分离 ✓）。

⚠️ **管理面已拆走** ✓（台账 **X16** ✓）—— 目录 / 策略 / 审核 / 趋势在
`admin_service.py` ✓（平面 B ✓）；这里只剩**运行时**要的 `recall` / `write`
✓ —— 对话路径的调用图里**不再出现平面 B** ✓（Stage 0 验收 ✓）。

⚠️ **本文件待拆** ✓ —— `recall` / `write` 的最终形态在契约层的
`memory/retrieval.py` / `memory/writer.py` ✓（Stage 2 / Stage 3 ✓）；
Stage 0 只做**平面分离** ✓（纯重构 ✓，行为不变 ✓）。
"""

from __future__ import annotations

from logging import getLogger
from uuid import UUID

from qzdap_agent_runtime.memory.extraction import RuleFactExtractor
from qzdap_agent_runtime.memory.redaction import RuleRedactor
from qzdap_agent_runtime.memory.retrieval import RetrievalPipeline
from qzdap_agent_runtime.memory.writer import WriteOutcome, WriterPipeline
from qzdap_agent_runtime.ports import RecallHit

from qzdap.modules.memory.adapter.candidates import (
    LexicalCandidateAdapter,
    VectorCandidateAdapter,
)
from qzdap.modules.memory.adapter.write_adapter import MemoryWriteAdapter
from qzdap.modules.memory.application.embedding import embed_item
from qzdap.modules.memory.application.ports import (
    EmbeddingPort,
    MemoryCatalogRepository,
    VectorSearchPort,
)

_log = getLogger(__name__)


class MemoryRuntimeService:
    """运行面 —— **召回 + 写入** ✓（不含任何管理查询 ✓）。"""

    def __init__(
        self,
        catalog: MemoryCatalogRepository,
        *,
        embedding: EmbeddingPort | None = None,
        vectors: VectorSearchPort | None = None,
        threshold: float = 0.15,
    ) -> None:
        self._catalog = catalog
        self._embedding = embedding
        self._vectors = vectors
        # ⚠️ **检索的编排归契约层** ✓ —— 这里只提供候选端口 ✓
        # （§3.1 的七步流水线 ✓）。
        self._pipeline = RetrievalPipeline(
            lexical=LexicalCandidateAdapter(catalog),
            vector=VectorCandidateAdapter(embedding=embedding, vectors=vectors),
            threshold=threshold,
        )
        #: 上一次召回是否**降级** ✓（C10 ✓ —— 调用方要能知道 ✓）。
        self._last_recall_degraded = False
        self._last_recall_reason = ""
        # ⚠️ **写入的编排归契约层** ✓ —— 这里只提供落库端口 ✓（§4.1 ✓）。
        self._writer_pipeline = WriterPipeline(
            extractor=RuleFactExtractor(),
            redactor=RuleRedactor(),
            store=MemoryWriteAdapter(
                catalog, embedding=embedding, vectors=vectors
            ),
        )

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
    ) -> WriteOutcome:
        """**新 Writer** ✓ —— 走契约层的五步流水线 ✓（Memory Stage 3 ✓）。

        ⚠️ **输入只有本轮对话** ✓（**不含召回结果** ✓ —— §4.6 ✓）；
        ⚠️ **闸门拒绝的要记下来** ✓（`rejected` ✓ —— 审计用 ✓）。
        """
        return await self._writer_pipeline.write_turn(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            user_id=user_id,
            session_id=session_id,
            turn_id=turn_id,
            user_input=user_input,
            assistant_reply=assistant_reply,
        )

    async def recall(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        query: str,
        top_k: int = 10,
        scope_filter: str | None = None,
        user_id: UUID | None = None,
    ) -> list[RecallHit]:
        """召回 ✓ —— **走契约层的七步流水线** ✓（Memory Stage 2 ✓）。

        ⚠️ **向量优先 + 词法兜底** ✓（§3.1 ✓）—— 不再全量扫描 ✓；
        ⚠️ **阈值 + abstain** ✓（§3.4 ✓）；
        ⚠️ **降级可见** ✓（C10 ✓）—— 向量不可用 → 纯词法 ✓ + ``degraded`` ✓。
        """
        _ = scope_filter
        outcome = await self._pipeline.recall(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            user_id=user_id,
            query=query,
            top_k=max(1, top_k),
        )
        self._last_recall_degraded = outcome.degraded
        self._last_recall_reason = outcome.degraded_reason
        return [
            RecallHit(
                layer=str(hit.get("layer") or "l2"),  # type: ignore[arg-type]
                content=str(hit.get("content") or ""),
                score=float(hit.get("score") or 0.0),
                source_id=str(hit.get("ref_id") or hit.get("id") or ""),
                citation=None,
                metadata={},
                scope=str(hit.get("scope") or "user"),
                used_count=int(hit.get("used_count") or 0),
                ref_id=str(hit.get("ref_id") or hit.get("id") or ""),
                version=str(hit.get("version") or ""),
            )
            for hit in outcome.hits
        ]

    async def _embed_item(
        self,
        item_id: UUID,
        layer: str,
        content: str,
        tenant_id: UUID,
        workspace_id: UUID,
        user_id: UUID | None = None,
    ) -> None:
        await embed_item(
            self._embedding,
            self._vectors,
            item_id=item_id,
            layer=layer,
            content=content,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            user_id=user_id,
        )


def _keyword_score(needle: str, hay: str) -> float:
    if not needle:
        return 0.1
    if needle in hay:
        return 1.0
    parts = [part for part in needle.split() if part]
    if not parts:
        return 0.05
    hits = sum(1 for part in parts if part in hay)
    return 0.15 + 0.85 * (hits / len(parts)) if hits else 0.05


def _hit(
    item_id: UUID,
    content: str,
    layer: str,
    score: float,
    *,
    used_count: int = 0,
    version: str = "",
) -> RecallHit:
    """一条召回命中 ✓ —— **统一用 ``RecallHit``** ✓（Memory Stage 0 · M-04 ✓）。

    ⚠️ **生产不再返回 dict** ✓ —— 返回形状统一 ✓（契约在
    ``qzdap_agent_runtime.ports`` ✓）；调用方要 dict 就自己转 ✓
    （agent_runtime 的适配器负责转 ✓）。
    """
    return RecallHit(
        layer=layer,  # type: ignore[arg-type]
        content=content,
        score=score,
        source_id=str(item_id),
        citation=None,
        metadata={},
        scope="workspace" if layer == "l3" else "user",
        used_count=used_count,
        ref_id=str(item_id),
        version=version,
    )


__all__ = ["MemoryRuntimeService"]
