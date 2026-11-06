"""``Evaluator`` —— **六个终止条件的单一判定点** ✓（Agent 方案 §3.3 / §3.4 ✓）。

⚠️ **必须全部兜住，且集中在一点** ✓（§3.4 ✓）—— 分散在各个节点里是
2026-10-15 那次重构失败的模式之一 ✗✗（每个 Stage 的验收都是「本节点单测通过」
✗ 但**没有一条测试跑完整个循环** ✗）。

| # | 条件 | 上限来源 | 触发后的行为 |
|---|---|---|---|
| 0 | 致命错误 | 模型调用失败 ✓ / 单步超时 ✓ | ``abort`` + 明确错误码 ✓ |
| 1 | 最大步数 | agent 配置 | ``abort`` + ``DEEP_AGENT_BUDGET_EXCEEDED`` ✓ |
| 2 | 最大成本 | ``max_cost_usd`` + ``base_cost_usd`` | ``abort`` ✓（决策 #7 的硬闸门 ✓ —— **会话级累计** ✓） |
| 3 | 上下文超限 | 模型报错 | ``abort`` + ``CONTEXT_TOO_LARGE`` ✓ |
| 4 | 用户取消 | ``session_turns.cancel_requested`` | ``abort`` ✓（产出部分结果 ✓） |
| 5 | 审批挂起 | 策略判定 | ``suspend`` ✓（→ ``interrupt()`` ✓） |
| 6 | 工具连续失败 / 空转 | 熔断器 ✓ / ``apply_stall_guard`` ✓ | ``exit`` + 明确错误 ✓ |
| 7 | 工具调用配额 | ``max_tool_calls`` | ``abort`` + 明确错误 ✓ |

⚠️ **闸门是「两级都有」** ✓（决策 #7 ✓）—— 轮次级是硬闸门 ✓；深度任务级
是它的一个子集 ✓（更深但仍有上限 ✓）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from langchain_core.messages import SystemMessage

from qzdap_kernel.error_codes import ErrorCode

from .state import LoopState

TerminationAction = Literal["continue", "suspend", "exit", "abort"]

#: **步数的硬上限** ✓（与旧路径同值 ✓ —— 决策 #7 的「两级都有」✓）。
HARD_MAX_STEPS = 16

#: **预算超限的错误码** ✓（方案 §3.3 ✓ —— ⚠️ 原先只是新 runtime 里的字符串
#: 常量 ✓ → **已提升为 `ErrorCode` 枚举成员** ✓ —— 前端不认识裸码 ✗）。
BUDGET_EXCEEDED = "DEEP_AGENT_BUDGET_EXCEEDED"


@dataclass(frozen=True, slots=True)
class Termination:
    """**一次判定** ✓。"""

    action: TerminationAction
    reason: str = ""
    error_code: str | None = None

    @property
    def should_continue(self) -> bool:
        return self.action == "continue"


class Evaluator:
    """**终止条件的单一判定点** ✓（§3.4 ✓）。"""

    def __init__(
        self,
        *,
        max_steps: int = 8,
        max_cost_usd: float = 0.0,
        base_cost_usd: float = 0.0,
        max_tool_calls: int = 0,
        stall_limit: int = 2,
    ) -> None:
        self._max_steps = max_steps
        self._max_cost_usd = max_cost_usd
        # ⚠️ **会话级累计** ✓ —— 之前那些轮已经花掉的 ✓（闸门要算上 ✓ ——
        # 只看这一轮的话 ✓ → 预算每轮重置 ✓ → 「一个会话烧掉一百倍的钱」
        # **没人拦得住** ✗✗）。
        self._base_cost_usd = base_cost_usd
        # ⚠️ **0 = 不限** ✓（与 ``max_cost_usd`` 同一口径 ✓）。
        self._max_tool_calls = max_tool_calls
        self._stall_limit = stall_limit

    def evaluate(
        self,
        state: LoopState,
        *,
        cancelled: bool = False,
        context_overflow: bool = False,
    ) -> Termination:
        """**判定下一步** ✓（六条一起判 ✓ —— 顺序 = 硬闸门优先 ✓）。"""
        # ① 用户取消 —— 立刻中断 ✓（产出部分结果 ✓）
        if cancelled:
            return Termination(
                "abort", reason="用户取消了这一轮", error_code=ErrorCode.TURN_CANCELLED.value
            )
        # ①' 致命错误 ✓（模型调用失败 ✓ / 单步超时 ✓）—— 排在取消之后 ✓
        # （其余条件之前 ✓ —— 失败原因要**原样带出去** ✓）。
        if state.fatal_error:
            return Termination(
                "abort",
                reason=str(state.fatal_error.get("message") or "本轮执行失败"),
                error_code=str(state.fatal_error.get("code") or "AGENT_LOOP_ABORTED"),
            )
        # ② 步数闸门 ✓
        if state.step > self._max_steps:
            return Termination(
                "abort",
                reason=f"超过最大步数 {self._max_steps}",
                error_code=BUDGET_EXCEEDED,
            )
        # ③ 成本闸门 ✓（决策 #7 的硬闸门 ✓ —— **会话级累计** ✓）
        session_cost = self._base_cost_usd + state.cost_usd
        if self._max_cost_usd > 0 and session_cost > self._max_cost_usd:
            return Termination(
                "abort",
                reason=f"超过成本上限 {self._max_cost_usd}",
                error_code=BUDGET_EXCEEDED,
            )
        # ③' 工具调用配额 ✓ —— 模型一次吐 N 个调用 ✓ → 全部执行 ✗✗
        # （成本 ✓ / 副作用 ✓ 都可能被放大 N 倍 ✗✗）。
        if self._max_tool_calls > 0 and state.tool_call_count > self._max_tool_calls:
            return Termination(
                "abort",
                reason=f"超过单轮工具调用上限 {self._max_tool_calls}",
                error_code=ErrorCode.AGENT_TOOL_QUOTA_EXCEEDED.value,
            )
        # ④ 上下文超限 ✓（连续两次仍超限 → 明确错误 ✓ —— §3.4 条件 3 ✓）
        if context_overflow:
            return Termination(
                "abort",
                reason="上下文超出模型上限",
                error_code=ErrorCode.CONTEXT_TOO_LARGE.value,
            )
        # ⑤ 审批挂起 ✓（挂起优先于继续 ✓ —— §3.5 ✓）
        if state.pending_approval:
            return Termination("suspend", reason="等待审批")
        # ⑥ 空转护栏 ✓（同样的工具连续空转 ✓ → 收尾 ✓）
        if state.stall_count >= self._stall_limit:
            return Termination(
                "exit",
                reason="相同工具连续空转",
                error_code=ErrorCode.TOOL_STALLED.value,
            )
        # ⑦ 没有工具调用 → 收尾 ✓
        if not state.tool_calls:
            return Termination("exit", reason="模型给出了最终回答")
        return Termination("continue")


def apply_stall_guard(state: LoopState, calls: list[dict[str, Any]]) -> LoopState:
    """**空转护栏** ✓（从旧路径**迁入** ✓ —— §8.2 ✓）。

    ⚠️ **同组工具调用重复出现就计数** ✓；到阈值就**插一句系统提示**让模型
    直接收尾 ✓（而不是继续空转 ✓）。
    """
    signatures = [_tool_signature(call) for call in calls]
    joined = "|".join(signatures)
    stall = state.stall_count + 1 if (joined and joined == state.last_tool_sig) else 0
    if stall >= 2:
        state.messages.append(
            SystemMessage(
                content="相同工具连续空转，请直接给出当前已知信息的最终回答，不要再调用工具。"
            )
        )
        state.pending_approval = None
    state.stall_count = stall
    state.last_tool_sig = joined
    return state


def _tool_signature(call: dict[str, Any]) -> str:
    """**一次工具调用的签名** ✓（名字 + 参数 ✓）。"""
    name = str(call.get("name") or (call.get("function") or {}).get("name") or "")
    arguments = call.get("arguments") or (call.get("function") or {}).get("arguments") or {}
    if not isinstance(arguments, dict):
        arguments = {}
    return f"{name}:{sorted((str(k), str(v)) for k, v in arguments.items())}"


__all__ = [
    "BUDGET_EXCEEDED",
    "HARD_MAX_STEPS",
    "Evaluator",
    "Termination",
    "apply_stall_guard",
]
