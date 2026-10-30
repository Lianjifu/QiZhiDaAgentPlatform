"""``Observer`` —— **工具结果 → 回灌消息** ✓（Agent 方案 §3.2 ✓）。

| # | 规则 |
|---|---|
| 1 | **失败的工具也要回灌** ✓ —— 模型需要知道「失败了、为什么」才能换策略 ✓ |
| 2 | **结果要截断** ✓ —— 本层只做**兜底上限** ✓（防单条消息撑爆内存 ✓） |
| 3 | **回灌顺序 = 请求顺序** ✓（模型的 ``tool_calls`` 数组顺序 ✓ —— 否则模型会误判因果 ✓） |
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from langchain_core.messages import ToolMessage


@dataclass(frozen=True, slots=True)
class ToolOutcome:
    """**一次工具执行的结果** ✓（回灌的输入 ✓）。"""

    tool_call_id: str
    name: str
    output: str
    is_error: bool = False


class Observer:
    """**把工具结果变成回灌消息** ✓（§3.2 ✓）。"""

    def __init__(self, *, max_output_chars: int = 8_000) -> None:
        self._max_output_chars = max_output_chars

    def messages(self, outcomes: Sequence[ToolOutcome]) -> list[ToolMessage]:
        """**回灌** ✓（顺序 = 给定的顺序 ✓ —— 规则 3 ✓）。"""
        return [
            ToolMessage(
                content=self._truncate(outcome.output),
                tool_call_id=outcome.tool_call_id,
                name=outcome.name,
                status="error" if outcome.is_error else "success",
            )
            for outcome in outcomes
        ]

    def _truncate(self, text: str) -> str:
        """**兜底截断** ✓（规则 2 ✓ —— 完整的截断策略归 Context 层 ✓）。"""
        if len(text) <= self._max_output_chars:
            return text
        return text[: self._max_output_chars] + "…（已截断）"


__all__ = ["Observer", "ToolOutcome"]
