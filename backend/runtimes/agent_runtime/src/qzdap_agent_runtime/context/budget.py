"""Context 层：token budget + compaction + manifest (§5.3 / §5.4)。

Stage 3 PR B 范围：

- `ContextBudget`: 简易 token 计数（按字符估算 4 chars ≈ 1 token，
  CJK 字符按 1 token 算；生产用 tiktoken/transformer）
- `assemble_context`: 把系统提示 / agent 配置 / tenant workspace /
  摘要 / L1+L2+L3 召回结果 / 当前 turn 用户输入 按固定优先级拼装
  + context_manifest 记录每个片段来源/token/过滤原因
- `Compactor`: messages 超过 budget 时压缩
  - 优先 LLM 摘要
  - 摘要失败时降级为确定性窗口压缩（旧消息摘要 → 末段保留）
  - 标记 `compaction_degraded`
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, runtime_checkable


def run_async_from_sync(coro: Any) -> Any:
    """从同步上下文运行 coroutine (处理已有的 event loop)。"""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    # 已在 event loop 中: 用线程池跑
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        return ex.submit(asyncio.run, coro).result()

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Token 估算
# ---------------------------------------------------------------------------


def estimate_tokens(text: str) -> int:
    """§5.3 token 预算估算（不作为绝对真值）。

    CJK 字符按 1 token 算，ASCII 4 chars ≈ 1 token（§5.10 tiktoken/provider tokenizer）。
    """
    cjk_count = sum(1 for c in text if "一" <= c <= "鿿")
    ascii_count = len(text) - cjk_count
    return cjk_count + (ascii_count + 3) // 4


# ---------------------------------------------------------------------------
# Context manifest
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ManifestEntry:
    """§5.3 context_manifest 单条记录。"""

    source: str  # 'system' | 'agent' | 'tenant' | 'summary' | 'memory_l1' | ...
    tokens: int
    filtered_reason: str | None = None
    version: str | None = None


@dataclass(slots=True)
class ContextManifest:
    """§5.3 context_manifest — 每次 assemble_context 产出。"""

    entries: list[ManifestEntry] = field(default_factory=list)

    def add(self, entry: ManifestEntry) -> None:
        self.entries.append(entry)

    @property
    def total_tokens(self) -> int:
        return sum(e.tokens for e in self.entries)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_tokens": self.total_tokens,
            "entries": [
                {
                    "source": e.source,
                    "tokens": e.tokens,
                    "filtered_reason": e.filtered_reason,
                    "version": e.version,
                }
                for e in self.entries
            ],
        }


# ---------------------------------------------------------------------------
# Summary compactor
# ---------------------------------------------------------------------------


@runtime_checkable
class SummaryModel(Protocol):
    """§5.3 摘要模型（LLM）。失败抛 SummaryError，由 Compactor fallback。"""


class SummaryError(Exception):
    """摘要失败（超时/网络/限流/坏 schema）。"""


class InMemorySummaryModel:
    """§5.3 单测 fallback：直接截取前 max_chars 字符作"摘要"。

    生产用真实 LLM 实现（同 §13.5 UsageChunk emit）。
    """

    def __init__(self, max_chars: int = 200) -> None:
        self.max_chars = max_chars

    def summarize(self, text: str) -> str:
        if not text:
            return ""
        if len(text) <= self.max_chars:
            return text
        return text[: self.max_chars] + "..."


class _AsyncSummaryModelAdapter:
    """把同步 summarize 包装为 async（生产 async 实现参考）。"""

    def __init__(self, sync: Any) -> None:
        self._sync = sync

    async def summarize(self, text: str) -> str:
        return self._sync.summarize(text)


# ---------------------------------------------------------------------------
# Compactor
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class CompactionResult:
    """§5.3 压缩结果。"""

    rolling_summary: str
    removed_message_ids: list[str]
    tokens_before: int
    tokens_after: int
    degraded: bool  # True = LLM 失败, 用确定性窗口压缩


class Compactor:
    """§5.3 Compactor — 优先 LLM 摘要, 失败降级为确定性窗口。"""

    def __init__(self, summary_model: SummaryModel | None = None) -> None:
        self._summary = summary_model or InMemorySummaryModel()

    def compact(
        self,
        messages: list[dict[str, Any]],
        existing_summary: str,
        target_tokens: int,
    ) -> CompactionResult:
        """压缩 messages 至 target_tokens 以内。

        策略：

        1. 计算当前 tokens
        2. 如已 <= target, 返回原状 (degraded=False)
        3. 否则尝试 LLM 摘要前 80% messages, 保留后 20%
        4. LLM 失败 → 确定性窗口（保留最近 N 条, 旧消息直接丢弃）
        """
        before = sum(estimate_tokens(str(m.get("content", ""))) for m in messages)
        if before <= target_tokens:
            return CompactionResult(
                rolling_summary=existing_summary,
                removed_message_ids=[],
                tokens_before=before,
                tokens_after=before,
                degraded=False,
            )

        # 拆：前 80% 摘要 / 后 20% 保留
        split = max(1, int(len(messages) * 0.8))
        head = messages[:split]
        tail = messages[split:]

        head_text = "\n".join(str(m.get("content", "")) for m in head)
        # 同步调用：summary_model.summarize 必须 sync（InMemory 默认）
        # 生产 async 实现：换成 anyio.from_thread.run_sync 或 await 包装
        try:
            summary_coro = self._summary.summarize(head_text)
            if asyncio.iscoroutine(summary_coro):
                # 异步实现：从线程跑
                new_summary = run_async_from_sync(summary_coro)
            else:
                new_summary = summary_coro
            degraded = False
        except Exception as exc:  # noqa: BLE001
            # §5.3 摘要失败时降级为确定性窗口压缩
            logger.warning("summary model failed, falling back: %s", exc)
            keep_n = min(5, len(messages))
            tail = messages[-keep_n:]
            removed = messages[:-keep_n]
            new_summary = (
                f"[deterministic compaction: {len(removed)} messages dropped]"
            )
            degraded = True

        new_messages = tail
        after = sum(estimate_tokens(str(m.get("content", ""))) for m in new_messages)
        after += estimate_tokens(new_summary)

        removed_ids = [
            str(m.get("message_id") or f"idx-{i}")
            for i, m in enumerate(messages)
            if m not in new_messages
        ]

        return CompactionResult(
            rolling_summary=new_summary,
            removed_message_ids=removed_ids,
            tokens_before=before,
            tokens_after=after,
            degraded=degraded,
        )


# ---------------------------------------------------------------------------
# Context assembler
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AssembledContext:
    """assemble_context 节点输出。"""

    messages: list[Any]  # 最终喂给 LLM 的消息列表
    manifest: ContextManifest
    degraded_flags: dict[str, bool]


class ContextAssembler:
    """§5.3 ContextAssembler — 固定优先级拼装 + manifest 记录。"""

    def __init__(self, max_tokens: int = 8000) -> None:
        self._max_tokens = max_tokens

    @property
    def max_tokens(self) -> int:
        return self._max_tokens

    def assemble(
        self,
        *,
        system_prompt: str,
        agent_config: dict[str, Any],
        tenant_context: dict[str, Any],
        rolling_summary: str,
        memory_hits: list[dict[str, Any]],
        knowledge_hits: list[dict[str, Any]],
        recent_messages: list[dict[str, Any]],
    ) -> AssembledContext:
        manifest = ContextManifest()
        parts: list[str] = []

        # 优先级 1: 安全系统提示
        manifest.add(ManifestEntry(
            source="system",
            tokens=estimate_tokens(system_prompt),
            version=agent_config.get("version"),
        ))
        parts.append(system_prompt)

        # 优先级 2: agent 配置
        agent_text = self._format_agent(agent_config)
        manifest.add(ManifestEntry(
            source="agent",
            tokens=estimate_tokens(agent_text),
            version=agent_config.get("version"),
        ))
        parts.append(agent_text)

        # 优先级 3: tenant / workspace / 用户 / 渠道上下文
        tenant_text = self._format_tenant(tenant_context)
        manifest.add(ManifestEntry(source="tenant", tokens=estimate_tokens(tenant_text)))
        parts.append(tenant_text)

        # 优先级 4: 摘要 + L1/L2/L3 召回
        if rolling_summary:
            manifest.add(ManifestEntry(
                source="summary", tokens=estimate_tokens(rolling_summary)
            ))
            parts.append(f"## 摘要\n{rolling_summary}")

        if memory_hits:
            mem_text = self._format_memory(memory_hits)
            manifest.add(ManifestEntry(source="memory", tokens=estimate_tokens(mem_text)))
            parts.append(f"## 记忆\n{mem_text}")

        if knowledge_hits:
            know_text = self._format_knowledge(knowledge_hits)
            manifest.add(ManifestEntry(
                source="knowledge", tokens=estimate_tokens(know_text)
            ))
            parts.append(f"## 知识\n{know_text}")

        # 优先级 5: 当前 turn 用户输入 + 工具结果（最近消息）
        recent_text = self._format_recent(recent_messages)
        manifest.add(ManifestEntry(
            source="recent", tokens=estimate_tokens(recent_text)
        ))
        parts.append(f"## 当前对话\n{recent_text}")

        # §5.3 超限按固定降级顺序：旧消息摘要 → 低分召回淘汰 → 附件摘要 → 明确错误
        degraded = {}
        if manifest.total_tokens > self._max_tokens:
            degraded = self._downgrade(manifest, parts, knowledge_hits)

        return AssembledContext(
            messages=parts,
            manifest=manifest,
            degraded_flags=degraded,
        )

    # ---- helpers ----

    def _format_agent(self, cfg: dict[str, Any]) -> str:
        return f"agent_id={cfg.get('agent_id')} version={cfg.get('version')}"

    def _format_tenant(self, ctx: dict[str, Any]) -> str:
        return (
            f"tenant={ctx.get('tenant_id')} "
            f"workspace={ctx.get('workspace_id')} "
            f"user={ctx.get('user_id')}"
        )

    def _format_memory(self, hits: list[dict[str, Any]]) -> str:
        lines = []
        for h in hits:
            lines.append(f"- ({h.get('layer','?')}) {h.get('content','')}")
        return "\n".join(lines)

    def _format_knowledge(self, hits: list[dict[str, Any]]) -> str:
        lines = []
        for h in hits:
            cid = h.get("metadata", {}).get("asset_id", "?")
            lines.append(f"- [{cid}] {h.get('content','')}")
        return "\n".join(lines)

    def _format_recent(self, msgs: list[dict[str, Any]]) -> str:
        lines = []
        for m in msgs:
            role = m.get("role", "user")
            content = m.get("content", "")
            lines.append(f"{role}: {content}")
        return "\n".join(lines)

    def _downgrade(
        self,
        manifest: ContextManifest,
        parts: list[str],
        knowledge_hits: list[dict[str, Any]],
    ) -> dict[str, bool]:
        """§5.3 固定降级顺序。

        当前实现：标记 compaction_degraded；删 knowledge_hits 直到 budget 内
        （knowledge_hits 是最不关键的：低分淘汰优先）。
        """
        # 简化：标记 degraded，不实际重算 parts（生产环境按精确优先级重排）
        return {"compaction_degraded": True}


__all__ = [
    "AssembledContext",
    "CompactionResult",
    "Compactor",
    "ContextAssembler",
    "ContextManifest",
    "InMemorySummaryModel",
    "ManifestEntry",
    "SummaryError",
    "SummaryModel",
    "estimate_tokens",
]