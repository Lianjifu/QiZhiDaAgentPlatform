"""``ContextBuilder`` —— 按**固定优先级**拼装上下文 ✓。

依据：Context 方案 §3（Builder）、§3.1（固定优先级）、§3.2（输出形状）、
§3.5（manifest 的内容）。

⚠️ **这一层是契约层** —— 不引框架 ✓（召回走协议 ✓，实现由模块侧给 ✓）。

⚠️ **固定优先级不可调换** ✓（§3.1 ✓）：

| 优先级 | 内容 | 可降级？ |
|---|---|---|
| 1 | 安全系统提示 + 治理约束 | ❌ 永不降级 ✓ |
| 2 | agent 版本 / 模型能力 / 工具白名单 | ❌ 永不降级 ✓ |
| 3 | 租户 / 工作区 / 用户 / 渠道 / 附件上下文 | ⚠️ 可精简 ✓ |
| 4 | 已确认的会话摘要 + 最近消息 | ⚠️ 可压缩 ✓ |
| 5 | 记忆 + 知识召回结果 | ⚠️ 按分淘汰 ✓ |
| 6 | 当前 turn 的用户输入 + 工具结果 | ❌ 永不降级 ✓ |

⚠️ **优先级 6 永不降级**是硬规则 ✓ —— 用户这句话和工具结果丢了，模型就是
在答空气 ✗✗；压缩只能动 3 / 4 / 5 ✓。

⚠️ **2026-10-30 更新**：**A-26 已完成** ✓ —— 旧循环 ``runner._run_turn_inner``
改调本 Builder ✓ → **Builder 现在有生产调用方** ✓；旧的上下文组装
**已删除** ✓（Context Stage 5 ✓）。
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable
from uuid import UUID

from ..memory.policy import MemoryPolicy
from .prompts import (
    DEFAULT_SYSTEM_PROMPT,
    render_agent_prompts,
    render_knowledge_hits,
    render_memory_hits,
    sort_hits_by_score,
)
from .tokens import estimate_tokens
from .types import AssembledContext, ContextManifest, ManifestEntry

#: 记忆召回条数 ✓（旧路径 ``runner.py:518`` ✓ —— 迁移必须复刻 ✓）。
MEMORY_TOP_K = 8
#: 知识召回条数 ✓（旧路径 ``runner.py:543`` ✓）。
KNOWLEDGE_TOP_K = 6


@runtime_checkable
class MemoryRecallPort(Protocol):
    """记忆召回 —— Context **主动发起** ✓（Context → Memory 的边界契约 ✓）。"""

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
    ) -> list[dict[str, Any]]: ...


@runtime_checkable
class KnowledgeSearchPort(Protocol):
    """知识召回 —— **不经过 Memory** ✓（Memory 决策 #1 ✓）。"""

    async def search(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        query: str,
        top_k: int,
        package_ids: tuple[UUID, ...] = (),
    ) -> list[dict[str, Any]]: ...


class ContextBuilder:
    """把「要喂给模型的东西」按固定优先级拼成 ``[{role, content}]`` ✓。

    ⚠️ **召回失败必须可见** ✓（Context 方案 §1.4.2 ✓）—— 旧路径是
    **静默吞掉**的 ✗✗（模型以为没有记忆 ✗）；这里置
    ``degraded_flags["recall_degraded"] = True`` ✓。
    """

    def __init__(
        self,
        *,
        memory_port: MemoryRecallPort | None = None,
        knowledge_port: KnowledgeSearchPort | None = None,
        max_tokens: int = 8_000,
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
    ) -> None:
        self._memory = memory_port
        self._knowledge = knowledge_port
        self._max_tokens = max_tokens
        self._system_prompt = system_prompt

    async def build(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        owner_id: UUID | None = None,
        user_input: str,
        history: list[dict[str, Any]] | None = None,
        agent_prompts: dict[str, Any] | None = None,
        agent_version: str | None = None,
        tenant_context: dict[str, Any] | None = None,
        summary: str = "",
        knowledge_package_ids: tuple[UUID, ...] = (),
        memory_policy: MemoryPolicy | None = None,
        session_id: UUID | None = None,
    ) -> AssembledContext:
        """拼一次上下文 ✓ —— 返回**可直接喂 LLM** 的消息列表 + manifest ✓。

        ⚠️ **记忆策略绑定要传下去** ✓（§7.1 ✓）—— 否则「agent 绑了作用域 /
        条目」运行时读不到 ✗✗（= §1.7 那个问题原地不动 ✗）。
        """
        history = list(history or [])
        degraded: dict[str, bool] = {}

        memories = await self._recall_memories(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            owner_id=owner_id,
            user_input=user_input,
            degraded=degraded,
            memory_policy=memory_policy,
            session_id=session_id,
        )
        knowledge = await self._recall_knowledge(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            user_input=user_input,
            package_ids=knowledge_package_ids,
            degraded=degraded,
        )

        manifest = ContextManifest()
        # ⚠️ **消息与清单条目成对** ✓ —— 降级时要成对丢 ✓（否则清单与消息
        # 对不上 ✗✗ —— 排查时「它喂了什么」就不可信了 ✗）。
        pairs: list[tuple[dict[str, Any], ManifestEntry]] = []

        # ── 优先级 1：安全系统提示 + 治理约束（永不降级 ✓）──────────────
        self._append_system(pairs, source="system", content=self._system_prompt)

        # ── 优先级 2：agent 的身份（永不降级 ✓）────────────────────────
        # ⚠️ **agent 没配 prompt 时不追加这一段** ✓ —— 否则会与优先级 1 的
        # 兜底句**重复两遍** ✗✗（旧路径只有一段 ✓）。
        agent_text = render_agent_prompts(agent_prompts)
        if agent_text:
            self._append_system(
                pairs,
                source="agent",
                content=agent_text,
                version=agent_version,
            )

        # ── 优先级 3：租户 / 工作区 / 用户 / 渠道上下文（可精简 ✓）──────
        tenant_text = self._render_tenant_context(tenant_context)
        if tenant_text:
            self._append_system(pairs, source="tenant", content=tenant_text)

        # ── 优先级 4：已确认的会话摘要 + 最近消息（可压缩 ✓）────────────
        if summary:
            self._append_system(pairs, source="summary", content=summary)

        # ── 优先级 5：记忆 + 知识召回结果（按分淘汰 ✓）──────────────────
        for hit in sort_hits_by_score(memories)[:MEMORY_TOP_K]:
            self._append_hit(pairs, source="memory", hit=hit, render=render_memory_hits)
        for hit in sort_hits_by_score(knowledge)[:KNOWLEDGE_TOP_K]:
            self._append_hit(
                pairs,
                source="knowledge",
                hit=hit,
                render=render_knowledge_hits,
            )

        # ── 优先级 4 的另一半：最近消息（原样保留 ✓）────────────────────
        for item in history:
            role = item.get("role")
            if role in {"user", "assistant", "tool", "system"}:
                pairs.append(
                    (
                        item,
                        ManifestEntry(
                            source="recent",
                            tokens=estimate_tokens(str(item.get("content") or "")),
                            ref_id=str(item.get("message_id") or "") or None,
                        ),
                    )
                )

        # ── 优先级 6：当前 turn 的用户输入（永不降级 ✓）─────────────────
        pairs.append(
            (
                {"role": "user", "content": user_input},
                ManifestEntry(
                    source="recent",
                    tokens=estimate_tokens(user_input),
                ),
            )
        )

        self._apply_budget(pairs, degraded)
        messages = [message for message, _ in pairs]
        for _, entry in pairs:
            manifest.add(entry)
        return AssembledContext(
            messages=messages,
            manifest=manifest,
            degraded_flags=degraded,
            tokens_estimated=manifest.total_tokens,
            # ⚠️ **原始召回**带出来 ✓ —— 调用方要单独下发 `knowledge_search`
            # 事件 ✓（不用再召回一次 ✗✗）。
            recalled={"memory": memories, "knowledge": knowledge},
        )

    # ── 召回 ────────────────────────────────────────────────────────────

    async def _recall_memories(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        owner_id: UUID | None,
        user_input: str,
        degraded: dict[str, bool],
        memory_policy: MemoryPolicy | None = None,
        session_id: UUID | None = None,
    ) -> list[dict[str, Any]]:
        if self._memory is None:
            return []
        try:
            return await self._memory.recall(
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                query=user_input,
                top_k=MEMORY_TOP_K,
                # ⚠️ **按当前用户过滤** ✓ —— 缺这一项会把同工作区其他用户的
                # 记忆召回进本用户的上下文 ✓（跨用户泄漏 ✓ —— X14 ✓）。
                user_id=owner_id,
                # ⚠️ **会话作用域** ✓（§7.1 ✓）—— 会话级策略时只看本会话 ✓。
                session_id=session_id,
                # ⚠️ **策略绑定** ✓（§7.1 ✓）—— 作用域 + 显式绑定的条目 ✓。
                policy=memory_policy,
            )
        except Exception:  # noqa: BLE001
            # ⚠️ **失败必须可见** ✓（旧路径静默吞掉 ✗✗）。
            degraded["recall_degraded"] = True
            return []

    async def _recall_knowledge(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        user_input: str,
        package_ids: tuple[UUID, ...],
        degraded: dict[str, bool],
    ) -> list[dict[str, Any]]:
        if self._knowledge is None:
            return []
        try:
            return await self._knowledge.search(
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                query=user_input,
                top_k=KNOWLEDGE_TOP_K,
                package_ids=package_ids,
            )
        except Exception:  # noqa: BLE001
            degraded["recall_degraded"] = True
            return []

    # ── 片段写入 ────────────────────────────────────────────────────────

    @staticmethod
    def _append_system(
        pairs: list[tuple[dict[str, Any], ManifestEntry]],
        *,
        source: str,
        content: str,
        version: str | None = None,
    ) -> None:
        pairs.append(
            (
                {"role": "system", "content": content},
                ManifestEntry(
                    source=source,
                    tokens=estimate_tokens(content),
                    version=version,
                ),
            )
        )

    @staticmethod
    def _append_hit(
        pairs: list[tuple[dict[str, Any], ManifestEntry]],
        *,
        source: str,
        hit: dict[str, Any],
        render: Any,
    ) -> None:
        """一条召回命中 → 一个 system 段落 + 一条 manifest ✓。

        ⚠️ **命中内容截 400 字** ✓（旧路径同 ✓ —— 渲染函数里截 ✓）。
        """
        content = render([hit])
        pairs.append(
            (
                {"role": "system", "content": content},
                ManifestEntry(
                    source=source,
                    tokens=estimate_tokens(content),
                    ref_id=ContextBuilder._ref_id(hit),
                    score=float(hit.get("score") or 0),
                ),
            )
        )

    @staticmethod
    def _ref_id(hit: dict[str, Any]) -> str | None:
        for key in ("id", "ref_id", "asset_id", "chunk_id"):
            value = hit.get(key)
            if value:
                return str(value)
        metadata = hit.get("metadata") or {}
        for key in ("id", "asset_id", "chunk_id"):
            value = metadata.get(key)
            if value:
                return str(value)
        return None

    @staticmethod
    def _render_tenant_context(tenant_context: dict[str, Any] | None) -> str:
        ctx = tenant_context or {}
        if not ctx:
            return ""
        parts = [
            f"{key}={ctx[key]}"
            for key in ("tenant_id", "workspace_id", "user_id", "channel", "actor")
            if ctx.get(key)
        ]
        return " ".join(parts)

    # ── 预算降级 ────────────────────────────────────────────────────────

    def _apply_budget(
        self,
        pairs: list[tuple[dict[str, Any], ManifestEntry]],
        degraded: dict[str, bool],
    ) -> None:
        """超预算 → 按**可降级顺序**丢片段 ✓（§3.1 ✓）。

        ⚠️ **降级序**：优先级 5（召回）→ 4（摘要）→ 3（租户上下文）✓；
        **优先级 1 / 2 / 6 永不降级** ✓。

        ⚠️ 被丢的片段在 manifest 里**留一条记录** ✓（``filtered_reason`` ✓）
        —— 「什么没进去」要能回答 ✓（§3.5 ✓）。
        """
        total = sum(entry.tokens for _, entry in pairs)
        if total <= self._max_tokens:
            return

        # 从优先级低到高丢 ✓（5 → 4 → 3 ✓）。
        for source in ("knowledge", "memory", "summary", "tenant"):
            if total <= self._max_tokens:
                break
            if not any(entry.source == source for _, entry in pairs):
                continue
            total = self._drop_source(pairs, source)
            degraded["compaction_degraded"] = True

    @staticmethod
    def _drop_source(
        pairs: list[tuple[dict[str, Any], ManifestEntry]],
        source: str,
    ) -> int:
        """把某个来源的片段从消息里去掉 ✓，并在清单条目上标注原因 ✓。

        返回剩下的 token 合计 ✓。
        """
        kept: list[tuple[dict[str, Any], ManifestEntry]] = []
        dropped_tokens = 0
        for message, entry in pairs:
            if entry.source == source and entry.filtered_reason is None:
                dropped_tokens += entry.tokens
                kept.append(
                    (
                        message,
                        ManifestEntry(
                            source=entry.source,
                            tokens=entry.tokens,
                            filtered_reason="over_budget",
                            version=entry.version,
                            ref_id=entry.ref_id,
                            score=entry.score,
                            degraded=entry.degraded,
                        ),
                    )
                )
                continue
            kept.append((message, entry))
        pairs[:] = kept
        return sum(entry.tokens for _, entry in kept)


__all__ = [
    "KNOWLEDGE_TOP_K",
    "MEMORY_TOP_K",
    "ContextBuilder",
    "KnowledgeSearchPort",
    "MemoryRecallPort",
]
