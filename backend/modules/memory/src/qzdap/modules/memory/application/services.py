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

from dataclasses import replace
from logging import getLogger
from uuid import UUID

from qzdap_agent_runtime.memory.extraction import RuleFactExtractor
from qzdap_agent_runtime.memory.policy import MemoryPolicy, RetentionPolicyView
from qzdap_agent_runtime.memory.redaction import RuleRedactor
from qzdap_agent_runtime.memory.retrieval import RetrievalPipeline
from qzdap_agent_runtime.memory.scope import MemoryScope
from qzdap_agent_runtime.memory.writer import WriteOutcome, WriterPipeline
from qzdap_agent_runtime.ports import RecallHit

from qzdap.modules.memory.adapter.candidates import (
    LexicalCandidateAdapter,
    PinnedCandidateAdapter,
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
            # ⚠️ **显式绑定的取法** ✓（§7.1 ✓）—— 没有它 = 管理端绑了没用 ✗✗。
            pinned=PinnedCandidateAdapter(catalog),
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
        policy: MemoryPolicy | None = None,
    ) -> WriteOutcome:
        """**新 Writer** ✓ —— 走契约层的五步流水线 ✓（Memory Stage 3 ✓）。

        ⚠️ **输入只有本轮对话** ✓（**不含召回结果** ✓ —— §4.6 ✓）；
        ⚠️ **闸门拒绝的要记下来** ✓（`rejected` ✓ —— 审计用 ✓）。

        ⚠️ **策略绑定在这一步生效** ✓（§7.1 ✓）—— ``enabled=False`` →
        **完全不写** ✓；作用域没有可写的层 → **明确跳过** ✓。
        """
        outcome = await self._writer_pipeline.write_turn(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            user_id=user_id,
            session_id=session_id,
            turn_id=turn_id,
            user_input=user_input,
            assistant_reply=assistant_reply,
            policy=policy,
        )
        if outcome.skipped or policy is None or not policy.policy_label:
            return outcome
        # ⚠️ **保留策略的绑定要看得见** ✓（§7.1 ✓）—— 标签解析成策略 ✓
        # （**执行者是淘汰器** ✓ —— Stage 6 ✓ —— 这里只把绑定解析出来 ✓）。
        retention = await self._resolve_retention(
            tenant_id=tenant_id, workspace_id=workspace_id, label=policy.policy_label
        )
        return replace(outcome, retention_label=retention.label if retention else "")

    async def _resolve_retention(
        self, *, tenant_id: UUID, workspace_id: UUID, label: str
    ) -> RetentionPolicyView | None:
        """``policyLabel`` → **保留策略** ✓（§7.1 ✓ —— 只读 ✓）。

        ⚠️ **查不到就是查不到** ✓ —— 不猜 ✓（没有默认策略兜底 ✗✗ ——
        猜一个 TTL 比没有更危险 ✓）。
        """
        try:
            policy = await self._catalog.get_policy_by_label(workspace_id, label)
        except Exception:  # noqa: BLE001
            _log.warning("memory retention policy lookup failed", extra={"label": label})
            return None
        if policy is None:
            return None
        return RetentionPolicyView(
            label=policy.label,
            layer=str(policy.layer),
            ttl_minutes=int(policy.ttl_minutes or 0),
            max_items=int(policy.max_items or 0),
            storage_mb=int(policy.storage_mb or 0),
            eviction=str(policy.eviction),
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
        session_id: UUID | None = None,
        policy: MemoryPolicy | None = None,
    ) -> list[RecallHit]:
        """召回 ✓ —— **走契约层的七步流水线** ✓（Memory Stage 2 ✓）。

        ⚠️ **向量优先 + 词法兜底** ✓（§3.1 ✓）—— 不再全量扫描 ✓；
        ⚠️ **阈值 + abstain** ✓（§3.4 ✓）；
        ⚠️ **降级可见** ✓（C10 ✓）—— 向量不可用 → 纯词法 ✓ + ``degraded`` ✓。
        """
        _ = scope_filter
        # ⚠️ **作用域由策略决定** ✓（§7.1 ✓）—— **不再只是标签** ✗✗：
        # - 会话级 → 只看**本会话**写的记忆 ✓；
        # - 用户级 → 该用户的记忆**跨会话可见** ✓（默认 ✓）。
        effective_session: UUID | None = None
        if policy is not None and policy.scope is MemoryScope.SESSION:
            effective_session = session_id
        outcome = await self._pipeline.recall(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            user_id=user_id,
            query=query,
            top_k=max(1, top_k),
            session_id=effective_session,
            extra_l3_entry_ids=policy.pinned_ids if policy is not None else (),
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
