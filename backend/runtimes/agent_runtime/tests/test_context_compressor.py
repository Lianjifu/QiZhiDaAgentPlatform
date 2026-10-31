"""Context Stage 2：``ContextCompressor`` —— async 压缩 + 两级降级。

依据：Context 方案 §4（Compressor）、§4.3（必须修掉的六个缺陷）、
§4.4（降级序固定）。

⚠️ **六个缺陷逐条有测试** ✓ —— 缺陷不消失就会回来 ✗✗。
"""

from __future__ import annotations

from typing import Any

import pytest

from qzdap_agent_runtime.context import (
    KEEP_RECENT,
    CompactionOutcome,
    ContextCompressor,
    ContextTooLargeError,
)


class _Summary:
    """摘要模型替身 ✓ —— 记住收到的提示词 ✓（要能断言「提示了什么」✗✗）。"""

    def __init__(self, text: str = "摘要内容", *, fail: bool = False):
        self.text = text
        self.fail = fail
        self.prompts: list[str] = []

    async def summarize(self, *, prompt: str) -> str:
        self.prompts.append(prompt)
        if self.fail:
            raise RuntimeError("summary model exploded")
        return self.text


def _messages(count: int, *, size: int = 50) -> list[dict[str, Any]]:
    return [
        {"role": "user" if i % 2 == 0 else "assistant", "content": "字" * size}
        for i in range(count)
    ]


class TestAsync:
    @pytest.mark.asyncio
    async def test_compact_is_awaitable(self) -> None:
        """压缩是 **async** ✓ —— 同步实现会**阻塞事件循环** ✗✗（缺陷 1 ✓）。"""
        compressor = ContextCompressor(summary_model=_Summary())
        result = await compressor.compact(messages=_messages(40), target_tokens=500)
        assert isinstance(result, CompactionOutcome)

    @pytest.mark.asyncio
    async def test_under_budget_is_left_alone(self) -> None:
        compressor = ContextCompressor(summary_model=_Summary())
        messages = _messages(3)
        result = await compressor.compact(messages=messages, target_tokens=10_000)
        assert result.degraded is False
        assert result.removed_ids == []
        assert result.tokens_before == result.tokens_after


class TestStructuredSummary:
    @pytest.mark.asyncio
    async def test_the_prompt_asks_for_the_four_things(self) -> None:
        """结构化摘要要保留：**决策 / 数字 / 承诺 / 未完成事项 / 来源 ID** ✓。"""
        summary = _Summary()
        compressor = ContextCompressor(summary_model=summary)
        await compressor.compact(messages=_messages(40), target_tokens=500)
        prompt = summary.prompts[0]
        for fragment in ("决策", "数字", "承诺", "未完成事项", "来源消息 ID"):
            assert fragment in prompt

    @pytest.mark.asyncio
    async def test_the_input_is_grouped_by_role(self) -> None:
        """摘要输入**按 role 分组** ✓ —— 全文拼接会丢结构 ✗（缺陷 4 ✓）。"""
        summary = _Summary()
        compressor = ContextCompressor(summary_model=summary)
        await compressor.compact(messages=_messages(40), target_tokens=500)
        prompt = summary.prompts[0]
        assert "[user]" in prompt
        assert "[assistant]" in prompt

    @pytest.mark.asyncio
    async def test_the_system_prompt_is_not_folded(self) -> None:
        """系统提示**不进摘要** ✓ —— 它是永不降级的那部分 ✓。"""
        summary = _Summary()
        compressor = ContextCompressor(summary_model=summary)
        messages = [{"role": "system", "content": "系统提示"}, *_messages(40)]
        await compressor.compact(messages=messages, target_tokens=500)
        assert "系统提示" not in summary.prompts[0]


class TestDegradationOrder:
    @pytest.mark.asyncio
    async def test_summary_failure_falls_back_to_the_window(self) -> None:
        """摘要失败 → **二级** ✓（不是继续喂超限上下文 ✗✗）。"""
        compressor = ContextCompressor(summary_model=_Summary(fail=True))
        result = await compressor.compact(messages=_messages(40), target_tokens=1500)
        assert result.degraded is True
        assert result.tokens_after <= 1500

    @pytest.mark.asyncio
    async def test_a_failed_summary_does_not_lose_the_folded_content(self) -> None:
        """摘要模型挂了 → **折掉的内容进确定性摘要** ✓（不是直接丢掉 ✗✗）。

        ⚠️ **拿空摘要去折消息 = 那一段对话直接消失** ✗✗ —— 摘要失败必须走
        二级（§4.2 ✓）。
        """
        compressor = ContextCompressor(summary_model=_Summary(fail=True))
        result = await compressor.compact(messages=_messages(40), target_tokens=1500)
        assert result.summary, "折掉的内容必须有地方可去"
        assert "字" in result.summary

    @pytest.mark.asyncio
    async def test_still_too_large_raises_instead_of_truncating(self) -> None:
        """仍超限 → **明确错误** ✓（决策 #5 ✓ —— 不静默截断 ✗✗）。"""
        compressor = ContextCompressor(summary_model=_Summary(fail=True))
        with pytest.raises(ContextTooLargeError) as excinfo:
            await compressor.compact(messages=_messages(200, size=500), target_tokens=10)
        assert excinfo.value.code == "CONTEXT_TOO_LARGE"

    @pytest.mark.asyncio
    async def test_the_existing_summary_is_appended_not_replaced(self) -> None:
        """降级时**追加**而不是覆盖 ✓ —— 覆盖等于丢掉此前所有轮次的结论 ✗✗。"""
        compressor = ContextCompressor(summary_model=_Summary(fail=True))
        result = await compressor.compact(
            messages=_messages(40), existing_summary="此前的结论", target_tokens=1500
        )
        assert "此前的结论" in result.summary

    @pytest.mark.asyncio
    async def test_the_summary_model_output_is_appended_too(self) -> None:
        compressor = ContextCompressor(summary_model=_Summary("新摘要"))
        result = await compressor.compact(
            messages=_messages(40), existing_summary="此前的结论", target_tokens=500
        )
        assert "此前的结论" in result.summary
        assert "新摘要" in result.summary


class TestRemovedIds:
    @pytest.mark.asyncio
    async def test_removed_ids_use_stable_sequences(self) -> None:
        """被移除的消息按**稳定序号**报 ✓（``session_seq`` ✓ —— 缺陷 3 ✓）。"""
        compressor = ContextCompressor(summary_model=_Summary())
        messages = [{"role": "user", "content": "字" * 50, "session_seq": i} for i in range(1, 41)]
        result = await compressor.compact(messages=messages, target_tokens=500)
        assert result.removed_ids
        assert all(rid.startswith("session_seq:") for rid in result.removed_ids)
        # 留下的最近消息不应出现在被移除列表里 ✓
        kept_seqs = {
            m.get("session_seq") for m in result.messages if m.get("session_seq") is not None
        }
        assert not kept_seqs & {int(rid.split(":")[1]) for rid in result.removed_ids}

    @pytest.mark.asyncio
    async def test_kept_recent_messages_survive(self) -> None:
        compressor = ContextCompressor(summary_model=_Summary())
        result = await compressor.compact(messages=_messages(40), target_tokens=500)
        body = [m for m in result.messages if m.get("role") != "system"]
        assert len(body) == KEEP_RECENT


class TestToolResultCleaning:
    @pytest.mark.asyncio
    async def test_long_tool_results_are_truncated(self) -> None:
        """工具结果**清洗** ✓ —— 超长的截 1500 字 ✓（缺陷 6 ✓）。"""
        compressor = ContextCompressor(summary_model=_Summary())
        messages = [
            *_messages(40),
            {"role": "tool", "content": "错误详情" + "x" * 5000},
        ]
        result = await compressor.compact(messages=messages, target_tokens=1_000)
        tool_messages = [m for m in result.messages if m.get("role") == "tool"]
        assert tool_messages
        assert all(len(m["content"]) <= 1501 for m in tool_messages)

    @pytest.mark.asyncio
    async def test_short_tool_results_are_left_alone(self) -> None:
        compressor = ContextCompressor(summary_model=_Summary())
        messages = [*_messages(40), {"role": "tool", "content": "短结果"}]
        result = await compressor.compact(messages=messages, target_tokens=500)
        tool_messages = [m for m in result.messages if m.get("role") == "tool"]
        assert tool_messages[0]["content"] == "短结果"


class TestBudget:
    def test_the_budget_is_seventy_percent_of_the_window(self) -> None:
        """预算 = 窗口 × 0.70 ✓（决策 #4 ✓ —— 不引入窗口表 ✓）。"""
        compressor = ContextCompressor(context_window=10_000)
        assert compressor.budget == 7000
