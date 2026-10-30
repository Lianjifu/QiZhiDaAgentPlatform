"""``Writer`` —— 记忆写入的**端口** ✓（C1）。

依据：Memory 方案 §4（写入五步 ✓）、§10.1（A2 ``writer.py`` ✓）。

⚠️ **这一层是契约层** —— 端口 + 结果形状 ✓（实现归模块侧 ✓）。

⚠️ **写入流水线**（§4.1 ✓）：抽取候选 → **敏感信息闸门** → 去重
（``content_hash`` ✓）→ 置信度 → 落库（带 provenance ✓）→ 写统计 ✓。

⚠️ **触发点是「一轮结束一次」** ✓（决策 #4 ✓）—— 不是每次 LLM 调用后 ✗。

⚠️ **输入只能是本轮的对话内容** ✓ —— ⚠️ **不能是召回结果** ✗✗（自我强化
循环 ✗ —— §4.6 ✓）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable
from uuid import UUID

from qzdap_agent_runtime.memory.extraction import FactExtractor
from qzdap_agent_runtime.memory.policy import MemoryPolicy
from qzdap_agent_runtime.memory.redaction import Redactor


@dataclass(frozen=True, slots=True)
class WriteOutcome:
    """一次写入的结果 ✓。"""

    #: 真正落库的几条 ✓。
    written: list[dict] = field(default_factory=list)
    #: 因**闸门**被拒的几条 ✓（要记审计 ✓ —— §4.3 ✓）。
    rejected: list[dict] = field(default_factory=list)
    #: 因**重复**被跳过（改为更新用量）的几条 ✓（§4.4 ✓）。
    deduplicated: list[dict] = field(default_factory=list)
    #: **整轮被跳过**的原因 ✓（§7.1 的策略绑定 ✓）—— 空串 = 没跳过 ✓。
    #: - ``policy_disabled`` ✓ —— agent 关了记忆 ✓；
    #: - ``scope_unsupported`` ✓ —— 作用域当前**没有可写的层** ✓（团队知识
    #:   还没迁走 ✓ —— 决策 #1 / M-47 ✓）—— **不静默降级**成写个人层 ✗✗。
    skipped: str = ""
    #: 这次写入用的**保留策略标签** ✓（``policyLabel`` ✓ —— 绑定要看得见 ✓）。
    retention_label: str = ""


@runtime_checkable
class Writer(Protocol):
    """记忆写入 ✓（C1 ✓）。"""

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
        policy: object | None = None,
    ) -> WriteOutcome:
        """把**本轮**对话沉淀成记忆 ✓（**不含召回结果** ✓ —— §4.6 ✓）。"""
        ...


__all__ = ["WriteOutcome", "Writer"]


# ---------------------------------------------------------------------------
# 写入流水线（§4.1 ✓）
# ---------------------------------------------------------------------------


#: 内容哈希的**规范化规则版本** ✓（§4.4 ✓ —— 规则变了要能区分 ✓）。
CONTENT_HASH_VERSION = 1


def normalize_content(content: str) -> str:
    """内容的**规范化** ✓（§4.4 ✓ —— 规则必须写死并版本化 ✓）。

    ① Unicode **NFKC** ✓（全角 → 半角 ✓）；② 折叠连续空白 ✓；
    ③ 去首尾空白 ✓；④ 转小写 ✓。

    ⚠️ **规则变了要升版本号** ✓ —— 否则同一内容不同写法 hash 不同 ✗✗
    （去重直接失效 ✗）。
    """
    import re
    import unicodedata

    folded = unicodedata.normalize("NFKC", content or "")
    collapsed = re.sub(r"\s+", " ", folded).strip().lower()
    return collapsed


def content_hash(content: str) -> str:
    """规范化内容的 sha256 ✓（§4.4 ✓）。"""
    import hashlib

    return hashlib.sha256(normalize_content(content).encode("utf-8")).hexdigest()


@runtime_checkable
class MemoryWritePort(Protocol):
    """记忆的落库口 ✓（模块侧实现 ✓ —— 契约层不碰数据库 ✓）。"""

    async def find_by_hash(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        user_id: UUID,
        content_hash: str,
    ) -> dict[str, Any] | None:
        """按内容哈希查已有条目 ✓（**去重的依据** ✓ —— §4.4 ✓）。"""
        ...

    async def save(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        user_id: UUID,
        session_id: UUID,
        turn_id: UUID | None,
        content: str,
        content_hash: str,
        confidence: float,
        confidence_source: str,
        category: str,
    ) -> dict[str, Any]:
        """落一条记忆 ✓（带来源与版本 ✓ —— §4.1 ✓）。"""
        ...

    async def touch(self, *, item_id: str) -> None:
        """命中重复时**更新用量** ✓（不新增 ✓ —— §4.4 ✓）。"""
        ...


class WriterPipeline:
    """写入的五步流水线 ✓（§4.1 ✓）。

    ① 抽取候选 → ② **敏感信息闸门** → ③ 去重（``content_hash`` ✓）→
    ④ 置信度 → ⑤ 落库（带 provenance ✓）。

    ⚠️ **输入只能是本轮对话** ✓（**不含召回结果** ✓ —— §4.6 ✓）。
    """

    def __init__(
        self,
        *,
        extractor: FactExtractor,
        redactor: Redactor,
        store: MemoryWritePort,
    ) -> None:
        self._extractor = extractor
        self._redactor = redactor
        self._store = store

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
        """沉淀一轮对话 ✓。

        ⚠️ **策略绑定在这一步生效** ✓（§7.1 ✓）—— ``enabled=False`` →
        **完全不写** ✓；作用域当前没有可写的层 → **明确跳过** ✓
        （**不静默降级** ✓ —— 悄悄改成写个人层 = 改了语义 ✗✗）。
        """
        if policy is not None:
            if not policy.enabled:
                return WriteOutcome(skipped="policy_disabled")
            if not policy.write_supported:
                return WriteOutcome(skipped="scope_unsupported")
        candidates = await self._extractor.extract(
            user_input=user_input, assistant_reply=assistant_reply
        )
        written: list[dict[str, Any]] = []
        rejected: list[dict[str, Any]] = []
        deduplicated: list[dict[str, Any]] = []

        for candidate in candidates:
            # ── ② 敏感信息闸门 ✓（命中 → 拒绝写入 ✓）──
            verdict = self._redactor.redact(candidate.content)
            if verdict.blocked:
                rejected.append(
                    {
                        "content": candidate.content,
                        "kinds": list(verdict.kinds),
                        "reason": verdict.reason,
                    }
                )
                continue

            digest = content_hash(candidate.content)

            # ── ③ 去重 ✓（命中已有 hash → 只更新用量 ✓）──
            existing = await self._store.find_by_hash(
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                user_id=user_id,
                content_hash=digest,
            )
            if existing is not None:
                await self._store.touch(item_id=str(existing.get("id") or ""))
                deduplicated.append({"id": existing.get("id"), "content": candidate.content})
                continue

            # ── ④⑤ 置信度 + 落库 ✓ ──
            saved = await self._store.save(
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                user_id=user_id,
                session_id=session_id,
                turn_id=turn_id,
                content=candidate.content,
                content_hash=digest,
                confidence=candidate.confidence,
                confidence_source=candidate.source,
                category=candidate.category,
            )
            written.append(saved)

        return WriteOutcome(
            written=written,
            rejected=rejected,
            deduplicated=deduplicated,
        )


__all__ = [
    "CONTENT_HASH_VERSION",
    "MemoryWritePort",
    "WriteOutcome",
    "Writer",
    "WriterPipeline",
    "content_hash",
    "normalize_content",
]
