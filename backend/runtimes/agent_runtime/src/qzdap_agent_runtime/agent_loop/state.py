"""``LoopState`` —— **一轮循环的状态** ✓（Agent 方案 §3 ✓）。

⚠️ **状态是「事实」不是「决策」** ✓ —— 判定归 ``evaluate.py`` 的单一判定点 ✓
（§3.4 ✓ —— 分散在各个节点里是 2026-10-15 那次重构失败的模式之一 ✗✗）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from langchain_core.messages import BaseMessage


@dataclass
class LoopState:
    """**循环状态** ✓（一轮之内累积 ✓）。"""

    #: 对话消息 ✓（含 system ✓ / 历史 ✓ / 工具结果 ✓）。
    messages: list[BaseMessage] = field(default_factory=list)
    #: **本步的模型工具调用** ✓（装配完成之后 ✓）。
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    #: **本步的工具结果** ✓（顺序 = 请求顺序 ✓ —— §3.2 规则 3 ✓）。
    tool_results: list[dict[str, Any]] = field(default_factory=list)
    #: **走到第几步了** ✓（步数闸门看它 ✓）。
    step: int = 0
    #: **这一轮花了多少钱** ✓（成本闸门看它 ✓ —— 决策 #7 的轮次级硬闸门 ✓）。
    cost_usd: float = 0.0
    #: **用量** ✓（input ✓ / output ✓）。
    input_tokens: int = 0
    output_tokens: int = 0
    #: **本步的用量** ✓（成本按步算 ✓ —— 钩子用得到 ✓）。
    step_input_tokens: int = 0
    step_output_tokens: int = 0
    #: **解析出来的模型 id** ✓（成本结算要它 ✓ —— 查表结果 ✓ 不是决策 ✓）。
    resolved_model_id: str | None = None
    #: **待审批的工具调用** ✓（挂起时非空 ✓ —— §3.5 ✓）。
    pending_approval: dict[str, Any] | None = None
    #: **本轮的任务清单** ✓（模型用 ``write_todos`` 维护 ✓）。
    #: ⚠️ **之前这个字段定义了但从未写入** ✓ —— 「规划」能力等于没有 ✗✗。
    #: ⚠️ **形状 = 每项 ``{"content", "status"}``** ✓（status ∈
    #: ``pending`` / ``in_progress`` / ``completed`` ✓）。
    todos: list[dict[str, Any]] = field(default_factory=list)
    #: **这一步选中的专家的指令** ✓（每步可换 ✓）。
    expert_instruction: str = ""
    #: **错误** ✓（终止时带上 ✓）。
    errors: list[dict[str, Any]] = field(default_factory=list)
    #: **模型的最终回答** ✓。
    final_message: str | None = None
    #: **空转计数** ✓（同一组工具调用重复出现 ✓ —— §3.4 条件 6 ✓）。
    stall_count: int = 0
    #: **上一组工具调用的签名** ✓（比它判断是不是「同样的空转」✓）。
    last_tool_sig: str = ""
    #: **结束了** ✓。
    done: bool = False


__all__ = ["LoopState"]
