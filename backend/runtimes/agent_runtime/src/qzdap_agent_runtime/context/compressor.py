"""``ContextCompressor`` —— 上下文压缩（**async**）✓。

依据：Context 方案 §4（Compressor）、§4.3（必须修掉的六个缺陷）。

⚠️ **这一层是契约层** —— 不引框架 ✓（摘要模型走协议 ✓）。

⚠️ **修掉的六个缺陷**（§4.3 ✓）：

| # | 缺陷 | 这里怎么修 |
|---|---|---|
| 1 | 同步实现阻塞事件循环 ✗ | ``compact()`` 是 **async** ✓；摘要模型走异步端口 ✓；旧 runtime 那条 ``run_async_from_sync`` 绕行路径**不再需要** ✓ |
| 2 | 压缩后不复验预算 ✗ | 压缩后**复验** ✓ → 仍超限 → 二级确定性窗口 ✓ → 仍超限 → **抛 ``CONTEXT_TOO_LARGE``** ✓（明确错误，不静默截断 ✓ —— 决策 #5 ✓） |
| 3 | ``removed_ids`` 按值包含算错 ✗ | 按**集合差**算 ✓（用稳定序号 ``session_seq`` ✓ —— 注意 ``session_messages`` **没有** ``message_id`` 列 ✗✗） |
| 4 | 摘要输入是全文拼接 ✗ | **按 role 分组**构造摘要输入 ✓（user / assistant / tool 分开 ✓），且只折叠「可折叠区」✓ |
| 5 | 确定性降级**覆盖** ``existing_summary`` ✗✗ | **追加**而不是替换 ✓（旧摘要是累加的 —— 覆盖等于丢掉此前所有轮次的结论 ✗✗） |
| 6 | 工具结果清洗缺失 ✗ | 复刻旧路径 ✓：工具错误 / 超长结果**截 1500 字** ✓ |

⚠️ **降级序固定**（§4.4 ✓）：旧消息摘要 → 低分召回淘汰 → 附件摘要 →
**明确错误（CONTEXT_TOO_LARGE）** ✓ —— 每一步淘汰都要记进 manifest 的
``filtered_reason`` ✓。

⚠️ **2026-10-30（Context Stage 4 接线时）修掉的两处** ✓：

| # | 症状 | 修法 |
|---|---|---|
| A | **摘要模型失败 → 拿空摘要去折消息** ✗✗ → 折掉的那段对话**直接消失** ✗ | 摘要失败**直接走二级** ✓（§4.2 ✓）—— 确定性摘要兜住内容 ✓ |
| B | **摘要的 token 被算两遍** ✗（``_fold`` 已经把它放进消息里了 ✓）→ 预算虚报 ✗ → 该压的没压、不该压的报超限 ✗ | ``tokens_after`` 只算**留下的那批消息** ✓ |
"""

from __future__ import annotations

import logging
from typing import Any, Protocol, runtime_checkable

from qzdap_kernel.errors import AppError
from qzdap_schema.dtos.errors import ErrorCode

from .tokens import estimate_message_tokens

_log = logging.getLogger(__name__)

#: 预算比例 ✓（沿用旧路径 ``compact.py`` 的 ``WINDOW_RATIO`` ✓ ——
#: 留 30% 给模型输出与工具结果 ✓；决策 #4 ✓ 不引入窗口表 ✓）。
WINDOW_RATIO = 0.70
#: 上下文窗口默认值 ✓（同旧路径 ✓）。
DEFAULT_WINDOW = 32_000
#: 压缩后**保留**的最近消息条数 ✓（旧路径 ``KEEP_RECENT = 6`` ✓）。
KEEP_RECENT = 6
#: 工具结果清洗的截断长度 ✓（旧路径 ``content[:1500]`` ✓ —— §4.3 缺陷 6 ✓）。
TOOL_RESULT_MAX_CHARS = 1500
#: 确定性降级时，每条消息的要点长度 ✓（旧路径 ``[:180]`` ✓）。
DETERMINISTIC_ITEM_CHARS = 180
#: 确定性降级时保留的要点条数 ✓（旧路径 ``[-20:]`` ✓）。
DETERMINISTIC_ITEMS = 20
#: 摘要自身的上限 ✓（旧路径 ``summary[-4000:]`` ✓）。
SUMMARY_MAX_CHARS = 4000


@runtime_checkable
class SummaryModelPort(Protocol):
    """摘要模型 —— **异步**端口 ✓（§4.3 缺陷 1 ✓）。

    ⚠️ 实现方要返回**结构化摘要** ✓ —— 保留决策 / 数字 / 承诺 / 未完成事项 /
    来源消息 ID ✓（§4.2 ✓）；提示词由实现方负责 ✓（端口只管调用 ✓）。
    """

    async def summarize(self, *, prompt: str) -> str: ...


class ContextTooLargeError(AppError):
    """压缩之后**仍然超预算** ✓ —— 明确错误 ✓（决策 #5 ✓）。"""

    code = ErrorCode.CONTEXT_TOO_LARGE.value
    status = 413


class CompactionOutcome:
    """一次压缩的结果 ✓。

    ⚠️ **不叫 ``CompactionResult``** ✓ —— 旧 runtime（``budget.py``）里
    还有一个同义但**语义不同**的类 ✓（那是待删的旧实现 ✓，Stage 5 删 ✓）
    —— 同名会让人以为是一套 ✗✗。
    """

    __slots__ = (
        "degraded",
        "messages",
        "removed_ids",
        "summary",
        "tokens_after",
        "tokens_before",
    )

    def __init__(
        self,
        *,
        messages: list[dict[str, Any]],
        summary: str,
        removed_ids: list[str],
        tokens_before: int,
        tokens_after: int,
        degraded: bool,
    ) -> None:
        self.messages = messages
        self.summary = summary
        self.removed_ids = removed_ids
        self.tokens_before = tokens_before
        self.tokens_after = tokens_after
        self.degraded = degraded

    def __repr__(self) -> str:  # pragma: no cover - 调试用
        return (
            f"CompactionOutcome(before={self.tokens_before}, after={self.tokens_after}, "
            f"degraded={self.degraded}, removed={len(self.removed_ids)})"
        )


class ContextCompressor:
    """上下文压缩 —— 一级摘要 / 二级确定性窗口 ✓（§4.2 ✓）。"""

    def __init__(
        self,
        *,
        summary_model: SummaryModelPort | None = None,
        context_window: int = DEFAULT_WINDOW,
    ) -> None:
        self._summary = summary_model
        self._context_window = context_window

    @property
    def budget(self) -> int:
        """预算 ✓ = 窗口 × 0.70 ✓（§4.1 ✓）。"""
        return max(1024, int(self._context_window * WINDOW_RATIO))

    async def compact(
        self,
        *,
        messages: list[dict[str, Any]],
        existing_summary: str = "",
        target_tokens: int | None = None,
    ) -> CompactionOutcome:
        """把消息压到预算以内 ✓。

        ⚠️ **不超预算就不压** ✓ —— 返回原状（``degraded=False`` ✓）。

        ⚠️ **压缩后复验** ✓ —— 仍超限 → 二级 → 仍超限 → **抛
        ``CONTEXT_TOO_LARGE``** ✓（不静默截断 ✓）。
        """
        target = target_tokens if target_tokens is not None else self.budget
        cleaned = self._clean_tool_results(messages)
        tokens_before = estimate_message_tokens(cleaned)
        if tokens_before <= target:
            return CompactionOutcome(
                messages=cleaned,
                summary=existing_summary,
                removed_ids=[],
                tokens_before=tokens_before,
                tokens_after=tokens_before,
                degraded=False,
            )

        # ── 一级：结构化摘要 ✓ ─────────────────────────────────────────
        summary, degraded = await self._summarize(cleaned, existing_summary)
        # ⚠️ **摘要失败 → 直接走二级** ✓（§4.2 ✓）—— 拿一个**空摘要**去折
        # 消息等于**把折掉的内容直接丢了** ✗✗（那一段对话就消失了 ✗）。
        if not degraded:
            kept, removed_ids = self._fold(cleaned, summary)
            # ⚠️ **摘要已经在那批消息里了** ✓（`_fold` 把它作为一条 system
            # 消息放进去 ✓）—— 再加一次就是**算两遍** ✗✗（预算被虚报 ✗
            # → 该压的没压、不该压的报超限 ✗）。
            tokens_after = estimate_message_tokens(kept)
            if tokens_after <= target:
                return CompactionOutcome(
                    messages=kept,
                    summary=summary,
                    removed_ids=removed_ids,
                    tokens_before=tokens_before,
                    tokens_after=tokens_after,
                    degraded=degraded,
                )

        # ── 二级：确定性窗口 ✓（§4.2 ✓）───────────────────────────────
        window_summary, window_removed = self._deterministic_summary(cleaned, existing_summary)
        window_kept, window_ids = self._fold(cleaned, window_summary)
        tokens_after = estimate_message_tokens(window_kept)
        if tokens_after <= target:
            return CompactionOutcome(
                messages=window_kept,
                summary=window_summary,
                removed_ids=window_ids + window_removed,
                tokens_before=tokens_before,
                tokens_after=tokens_after,
                degraded=True,
            )

        # ── 明确错误 ✓（决策 #5 ✓）────────────────────────────────────
        raise ContextTooLargeError(
            f"context too large after compaction: {tokens_after} > {target}",
            details={"tokens_before": tokens_before, "tokens_after": tokens_after},
        )

    # ── 一级：摘要 ──────────────────────────────────────────────────────

    async def _summarize(
        self, messages: list[dict[str, Any]], existing_summary: str
    ) -> tuple[str, bool]:
        """生成**结构化摘要** ✓ → ``(摘要, 是否降级)`` ✓。"""
        if self._summary is None:
            return existing_summary, True
        prompt = self._build_summary_prompt(messages, existing_summary)
        try:
            summary = await self._summary.summarize(prompt=prompt)
        except Exception:
            # ⚠️ 摘要失败 → 二级 ✓（不是继续喂超限上下文 ✗✗）。
            _log.warning("summary model failed — falling back to deterministic window")
            return existing_summary, True
        summary = str(summary or "").strip()
        if not summary:
            return existing_summary, True
        # ⚠️ **追加**而不是替换 ✓（缺陷 5 ✓）—— 旧摘要是累加的 ✓。
        merged = f"{existing_summary}\n\n{summary}" if existing_summary else summary
        return merged[:SUMMARY_MAX_CHARS], False

    @staticmethod
    def _build_summary_prompt(messages: list[dict[str, Any]], existing_summary: str) -> str:
        """摘要输入 —— **按 role 分组** ✓（缺陷 4 ✓），只取**可折叠区** ✓。"""
        groups: dict[str, list[str]] = {"user": [], "assistant": [], "tool": []}
        foldable = ContextCompressor._foldable_region(messages)
        for message in foldable:
            role = str(message.get("role") or "user")
            content = str(message.get("content") or "")
            if role not in groups:
                groups.setdefault(role, [])
            groups[role].append(content)
        parts = [
            (
                "请把下面的对话压缩成结构化摘要，必须保留："
                "① 决策与结论（含数字、承诺、期限）；② 未完成事项；"
                "③ 关键实体（人名、单号、参数）；④ 来源消息 ID。"
            ),
        ]
        if existing_summary:
            parts.append(f"\n已有摘要（保留并合并）：\n{existing_summary}")
        for role, contents in groups.items():
            if not contents:
                continue
            parts.append(f"\n[{role}]\n" + "\n".join(contents))
        return "\n".join(parts)

    @staticmethod
    def _foldable_region(
        messages: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """「可折叠区」= **除最近 KEEP_RECENT 条之外**的消息 ✓。

        ⚠️ **系统提示不进摘要** ✓ —— 它是永不降级的那部分 ✓（§3.1 ✓）。
        """
        body = [m for m in messages if m.get("role") != "system"]
        return body[:-KEEP_RECENT] if len(body) > KEEP_RECENT else []

    def _fold(
        self, messages: list[dict[str, Any]], summary: str
    ) -> tuple[list[dict[str, Any]], list[str]]:
        """折叠「可折叠区」→ 摘要段 ✓，留下最近的消息 ✓。

        返回 ``(留下的消息, 被移除的稳定序号)`` ✓。
        """
        system = [m for m in messages if m.get("role") == "system"]
        body = [m for m in messages if m.get("role") != "system"]
        keep = body[-KEEP_RECENT:] if len(body) > KEEP_RECENT else body
        folded = body[:-KEEP_RECENT] if len(body) > KEEP_RECENT else []
        removed_ids = [self._stable_id(m, index) for index, m in enumerate(folded)]

        kept = list(system)
        if summary:
            kept.append({"role": "system", "content": f"更早轮次摘要：{summary}"})
        kept.extend(keep)
        return kept, removed_ids

    # ── 二级：确定性窗口 ────────────────────────────────────────────────

    def _deterministic_summary(
        self, messages: list[dict[str, Any]], existing_summary: str
    ) -> tuple[str, list[str]]:
        """确定性降级摘要 ✓ —— **追加**而不是覆盖 ✓（缺陷 5 ✓）。"""
        foldable = self._foldable_region(messages)
        digest_parts: list[str] = []
        for message in foldable:
            role = str(message.get("role") or "")
            text = str(message.get("content") or "").replace("\n", " ")[:DETERMINISTIC_ITEM_CHARS]
            if text:
                digest_parts.append(f"{role}: {text}")
        if not digest_parts:
            return existing_summary, []
        digest = " | ".join(digest_parts[-DETERMINISTIC_ITEMS:])
        # ⚠️ **追加** ✓（缺陷 5 ✓）—— 覆盖等于丢掉此前所有轮次的结论 ✗✗。
        merged = f"{existing_summary}\n\n{digest}" if existing_summary else digest
        return merged[:SUMMARY_MAX_CHARS], []

    # ── 工具结果清洗 ────────────────────────────────────────────────────

    @staticmethod
    def _clean_tool_results(
        messages: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """工具结果清洗 ✓（缺陷 6 ✓）—— 复刻旧路径 ✓。

        旧路径的判据 ✓：``role == "tool"`` 且（以 ``ERROR`` 开头 ✓ 或含
        ``SKILL_DENIED`` ✓ 或长度 > 4000 ✓）→ 内容截到 **1500** 字 ✓。
        """
        cleaned: list[dict[str, Any]] = []
        for item in messages:
            role = item.get("role")
            content = str(item.get("content") or "")
            if role == "tool" and (
                content.startswith("ERROR") or "SKILL_DENIED" in content or len(content) > 4000
            ):
                item = {
                    **item,
                    "content": content[:TOOL_RESULT_MAX_CHARS]
                    + ("…" if len(content) > TOOL_RESULT_MAX_CHARS else ""),
                }
            cleaned.append(item)
        return cleaned

    @staticmethod
    def _stable_id(message: dict[str, Any], index: int) -> str:
        """被移除消息的**稳定标识** ✓（缺陷 3 ✓）。

        ⚠️ 优先用 ``session_seq`` ✓（会话内单调 ✓ —— 迁移 0046 ✓）；
        ⚠️ **没有** ``message_id`` 列 ✗✗ → 退化成序号占位 ✓。
        """
        for key in ("session_seq", "seq"):
            value = message.get(key)
            if value is not None:
                return f"{key}:{value}"
        return f"idx:{index}"


__all__ = [
    "DEFAULT_WINDOW",
    "DETERMINISTIC_ITEMS",
    "DETERMINISTIC_ITEM_CHARS",
    "KEEP_RECENT",
    "SUMMARY_MAX_CHARS",
    "TOOL_RESULT_MAX_CHARS",
    "WINDOW_RATIO",
    "CompactionOutcome",
    "ContextCompressor",
    "ContextTooLargeError",
    "SummaryModelPort",
]
