"""``AgentLoopRunner`` —— **循环本体** ✓（Agent 方案 §3 ✓ / §8.1 ✓）。

```
Reason（模型流式输出 ✓）
   → Evaluate（六个终止条件的单一判定点 ✓）
      → continue → 执行工具（治理 ✓ → 幂等 ✓）
         → Observe（结果回灌 ✓）
            → Evaluate …
      → exit    → 收尾 ✓
      → suspend → 审批挂起 ✓
      → abort   → 明确错误 ✓
```

⚠️ **治理在执行之前** ✓（§3.5 ✓）—— 判定**在** `PolicyGuard` ✓ —— 本层
**只调它** ✓（决策在 Governance ✓ —— 落地在 Session ✓）。

⚠️ **actor 是真实调用者** ✓ —— 取不到就**拒绝执行工具** ✓（§3.5 的洞 ✓ ——
**不用假 actor 继续** ✗✗）。
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from langchain_core.messages import BaseMessage
from langchain_core.tools import BaseTool
from pydantic import create_model

from qzdap_kernel.digest import request_hash
from qzdap_kernel.error_codes import ErrorCode

from ..execution.tool_binding import (
    reset_current_actor,
    reset_current_tool_scope,
    set_current_actor,
    set_current_tool_scope,
)
from ..ports import (
    ActorContext,
    PolicyGuard,
    ToolBinding,
    ToolCallOutput,
    ToolMeta,
)
from .evaluate import Evaluator, Termination, apply_stall_guard
from .observe import Observer, ToolOutcome
from .reason import Reasoner
from .state import LoopState

LoopEventKind = Literal[
    "text",
    "tool_call",
    "tool_result",
    "approval_required",
    "final",
    "error",
    "usage",
    "extra",
]


@dataclass(frozen=True, slots=True)
class LoopEvent:
    """**循环产出的一条事件** ✓（模块侧翻译成 chunk ✓）。"""

    kind: LoopEventKind
    text: str = ""
    tool_call: dict[str, Any] | None = None
    tool_result: dict[str, Any] | None = None
    approval: dict[str, Any] | None = None
    error_code: str | None = None
    error_message: str = ""
    usage: dict[str, int] = field(default_factory=dict)
    #: **旁路载荷** ✓（钩子带出来的东西 ✓ —— 本层不解释它 ✓）。
    payload: Any = None


@dataclass(frozen=True, slots=True)
class LoopHooks:
    """**每步的旁路钩子** ✓。

    ⚠️ **循环本体不碰业务** ✓ —— 上下文压缩 ✓ / manifest 落库 ✓ / 成本结算 ✓ /
    旁路事件 ✓ 都归调用方 ✓ —— 这里只给它们一个**按步调用的位置** ✓。
    """

    #: **推理之前** ✓（压缩上下文 ✓ —— 钩子可以就地改 ``state.messages`` ✓）。
    before_step: Callable[[LoopState], AsyncIterator[Any]] | None = None
    #: **推理之后** ✓（落库 ✓ / 算成本 ✓ / 旁路事件 ✓）。
    after_step: Callable[[LoopState], AsyncIterator[Any]] | None = None


@dataclass(frozen=True, slots=True)
class BoundTool:
    """**绑定好的工具** ✓（工具 ✓ + 它的治理元数据 ✓）。"""

    tool: BaseTool
    binding: ToolBinding


class AgentLoopRunner:
    """**Reason → Observe → Evaluate** ✓（§3 ✓）。"""

    def __init__(
        self,
        *,
        reasoner: Reasoner,
        evaluator: Evaluator | None = None,
        observer: Observer | None = None,
        policy_guard: PolicyGuard | None = None,
        actor: ActorContext | None = None,
        turn_id: str | None = None,
        session_id: str | None = None,
        protected: bool = True,
        allow_approval: bool = True,
        cost_of: Callable[[int, int], float] | None = None,
        hooks: LoopHooks | None = None,
    ) -> None:
        self._reasoner = reasoner
        self._evaluator = evaluator or Evaluator()
        self._observer = observer or Observer()
        self._policy_guard = policy_guard
        self._actor = actor
        self._turn_id = turn_id
        self._session_id = session_id
        self._protected = protected
        # ⚠️ **这一轮能不能挂起审批** ✓ —— IM 渠道关掉它 ✓（没有人能完成
        # 审批 ✓ → 挂起一个永远不会被批准的审批 = **这一轮卡死** ✗✗）。
        self._allow_approval = allow_approval
        self._cost_of = cost_of
        self._hooks = hooks

    async def run(
        self,
        *,
        messages: Sequence[BaseMessage],
        tools: Sequence[BoundTool],
        cancelled: Callable[[], bool] | None = None,
    ) -> AsyncIterator[LoopEvent]:
        """**跑一轮** ✓（产出事件流 ✓）。"""
        state = LoopState(messages=list(messages))
        by_name = {bound.tool.name: bound for bound in tools}
        while True:
            state.step += 1
            state.tool_calls = []
            state.step_input_tokens = 0
            state.step_output_tokens = 0
            if self._hooks is not None and self._hooks.before_step is not None:
                async for payload in self._hooks.before_step(state):
                    yield LoopEvent(kind="extra", payload=payload)
            async for event in self._reason(state, by_name):
                yield event
            state.input_tokens += state.step_input_tokens
            state.output_tokens += state.step_output_tokens
            if self._hooks is not None and self._hooks.after_step is not None:
                async for payload in self._hooks.after_step(state):
                    yield LoopEvent(kind="extra", payload=payload)

            termination = self._evaluator.evaluate(
                state,
                cancelled=bool(cancelled and cancelled()),
            )
            if termination.action in {"exit", "abort", "suspend"}:
                async for event in self._finish(state, termination):
                    yield event
                return

            # ── 执行工具（治理 → 执行） ──────────────────────────────
            outcomes: list[ToolOutcome] = []
            for call in state.tool_calls:
                bound = by_name.get(str(call.get("name") or ""))
                if bound is None:
                    outcome = ToolOutcome(
                        tool_call_id=str(call.get("id") or ""),
                        name=str(call.get("name") or ""),
                        output=f"工具 {call.get('name')!r} 没有绑定",
                        is_error=True,
                    )
                    outcomes.append(outcome)
                    yield LoopEvent(
                        kind="tool_result",
                        tool_result={
                            "tool_call_id": outcome.tool_call_id,
                            "name": outcome.name,
                            "output": outcome.output,
                            "is_error": outcome.is_error,
                        },
                    )
                    continue
                approval = await self._approval_for(call, bound)
                if approval is not None:
                    state.pending_approval = approval
                    termination = self._evaluator.evaluate(state)
                    yield LoopEvent(kind="approval_required", approval=approval, payload=state)
                    async for event in self._finish(state, termination):
                        yield event
                    return
                outcome = await self._invoke(call, bound)
                outcomes.append(outcome)
                yield LoopEvent(
                    kind="tool_result",
                    tool_result={
                        "tool_call_id": outcome.tool_call_id,
                        "name": outcome.name,
                        "output": outcome.output,
                        "is_error": outcome.is_error,
                        # ⚠️ **产物走独立的键** ✓（不进 ``output`` ✓）——
                        # 模块侧据此落库 ✓（契约层不碰 DB ✓）。
                        "artifact": outcome.artifact,
                    },
                )
            state.tool_results = [
                {
                    "tool_call_id": outcome.tool_call_id,
                    "name": outcome.name,
                    "output": outcome.output,
                    "is_error": outcome.is_error,
                }
                for outcome in outcomes
            ]
            state.messages.extend(self._observer.messages(outcomes))
            state = apply_stall_guard(state, state.tool_calls)

    # ── Reason ─────────────────────────────────────────────────────────

    async def _reason(
        self, state: LoopState, by_name: dict[str, BoundTool]
    ) -> AsyncIterator[LoopEvent]:
        """**跑一步推理** ✓（流式文本 ✓ + 工具调用 ✓）。"""
        schemas = [tool_schema(bound.tool) for bound in by_name.values()]
        text_parts: list[str] = []
        async for chunk in self._reasoner.reason(messages=state.messages, tools=schemas):
            if chunk.content:
                text = _as_text(chunk.content)
                text_parts.append(text)
                yield LoopEvent(kind="text", text=text)
            if chunk.tool_calls:
                state.tool_calls = [dict(call) for call in chunk.tool_calls]
                for call in state.tool_calls:
                    yield LoopEvent(kind="tool_call", tool_call=call)
            usage = getattr(chunk, "usage_metadata", None)
            if usage:
                # ⚠️ **用量取本步最后一份** ✓（与旧路径同口径 ✓）—— 多个 chunk
                # 都带用量时**不重复累加** ✓。
                state.step_input_tokens = int(usage.get("input_tokens") or 0)
                state.step_output_tokens = int(usage.get("output_tokens") or 0)
                if self._cost_of is not None:
                    state.cost_usd += self._cost_of(
                        state.step_input_tokens,
                        state.step_output_tokens,
                    )
                yield LoopEvent(
                    kind="usage",
                    usage={
                        "input_tokens": state.step_input_tokens,
                        "output_tokens": state.step_output_tokens,
                    },
                )
        state.final_message = "".join(text_parts) or state.final_message

    # ── 治理与执行 ─────────────────────────────────────────────────────

    async def _approval_for(self, call: dict[str, Any], bound: BoundTool) -> dict[str, Any] | None:
        """**这个工具要不要审批** ✓（§3.5 ✓）。

        ⚠️ **治理是默认路径** ✓ —— 有 ``PolicyGuard`` 就**每个工具都问一遍**
        ✓（拒绝要拦在执行之前 ✓）；没有 guard 才按绑定声明判
        （``requires_approval`` ✓）。

        ⚠️ **这一轮不能挂起审批时（IM 渠道 ✓）→ 直接拒绝** ✓ —— 不是挂起
        一个**永远不会被批准**的审批 ✓（那等于**卡死这一轮** ✗✗）。
        """
        arguments = call.get("args") or {}
        if not isinstance(arguments, dict):
            arguments = {}
        approval_id: str | None = None
        if self._policy_guard is not None:
            decision, approval_id = await self._policy_guard.decide(
                actor=self._actor,  # type: ignore[arg-type]
                tool_call_id=str(call.get("id") or ""),
                tool_meta=_tool_meta(bound),
                arguments=dict(arguments),
            )
            if decision == "deny":
                return {
                    "denied": True,
                    "tool_call_id": str(call.get("id") or ""),
                    "tool_name": bound.tool.name,
                    "arguments": dict(arguments),
                    "request_hash": request_hash(arguments),
                    "reason": "治理拒绝执行该工具",
                }
            if decision == "allow":
                return None
            if decision == "approve_required" and not self._allow_approval:
                # ⚠️ **策略要审批 + 这一轮不能挂起** ✓ → **明确拒绝** ✓
                # （不是挂起 ✓ —— 挂了没人批 ✓ = 卡死 ✗✗）。
                return {
                    "denied": True,
                    "tool_call_id": str(call.get("id") or ""),
                    "tool_name": bound.tool.name,
                    "arguments": dict(arguments),
                    "request_hash": request_hash(arguments),
                    "reason": "这个工具需要人工审批，当前渠道无法完成审批",
                }
        if not bound.binding.requires_approval:
            return None
        if not self._allow_approval:
            return {
                "denied": True,
                "tool_call_id": str(call.get("id") or ""),
                "tool_name": bound.tool.name,
                "arguments": dict(arguments),
                "request_hash": request_hash(arguments),
                "reason": "这个工具需要人工审批，当前渠道无法完成审批",
            }
        return {
            "approval_id": approval_id or "",
            "tool_call_id": str(call.get("id") or ""),
            "tool_name": bound.tool.name,
            "arguments": dict(arguments),
            "request_hash": request_hash(arguments),
            "reason": "高风险操作需要确认",
        }

    async def _invoke(self, call: dict[str, Any], bound: BoundTool) -> ToolOutcome:
        """**执行一次工具** ✓（真实 actor ✓ —— 取不到就拒绝 ✓）。"""
        if self._actor is None:
            return ToolOutcome(
                tool_call_id=str(call.get("id") or ""),
                name=bound.tool.name,
                output="没有真实调用者，不许执行工具",
                is_error=True,
            )
        arguments = call.get("args") or {}
        if not isinstance(arguments, dict):
            arguments = {}
        call_id = str(call.get("id") or "")
        scope_token = set_current_tool_scope(
            _scope(
                call_id=call_id,
                turn_id=self._turn_id,
                session_id=self._session_id,
                protected=self._protected,
            )
        )
        actor_token = set_current_actor(self._actor)
        try:
            result = await bound.tool.ainvoke(dict(arguments))
        except Exception as exc:
            return ToolOutcome(
                tool_call_id=call_id,
                name=bound.tool.name,
                output=f"{type(exc).__name__}: {exc}",
                is_error=True,
            )
        finally:
            reset_current_tool_scope(scope_token)
            reset_current_actor(actor_token)
        # ⚠️ **工具回的是「文本 + 产物」** ✓（``ToolCallOutput`` ✓）——
        # 产物**另带一格** ✓（不进文本 ✓ —— 文本要回灌给模型 ✓）。
        if isinstance(result, ToolCallOutput):
            return ToolOutcome(
                tool_call_id=call_id,
                name=bound.tool.name,
                output=result.text,
                is_error=False,
                artifact=result.artifact,
            )
        return ToolOutcome(
            tool_call_id=call_id,
            name=bound.tool.name,
            output=str(result),
            is_error=False,
        )

    # ── 收尾 ───────────────────────────────────────────────────────────

    async def _finish(self, state: LoopState, termination: Termination) -> AsyncIterator[LoopEvent]:
        """**收尾** ✓（exit ✓ / abort ✓ / suspend ✓）。"""
        if termination.action == "abort":
            yield LoopEvent(
                kind="error",
                error_code=termination.error_code or "AGENT_LOOP_ABORTED",
                error_message=termination.reason,
            )
            return
        if termination.action == "suspend":
            approval = state.pending_approval or {}
            if approval.get("denied"):
                yield LoopEvent(
                    kind="error",
                    error_code=ErrorCode.TOOL_DENIED.value,
                    error_message=str(approval.get("reason") or "治理拒绝执行该工具"),
                )
            return
        yield LoopEvent(kind="final", text=state.final_message or "", payload=state)


def tool_schema(tool: BaseTool) -> dict[str, Any]:
    """**工具 → 模型的工具 schema** ✓（OpenAI 形状 ✓）。"""
    from ..execution.tool_binding import tool_schema as _schema

    return _schema(tool)


def _tool_meta(bound: BoundTool) -> ToolMeta:
    """**绑定 → 治理用的元数据** ✓。"""
    binding = bound.binding
    return ToolMeta(
        name=binding.name,
        description=str(binding.spec.get("description") or binding.name),
        args_schema=_model_from_schema(binding.spec),
        risk=binding.risk,
        requires_approval=binding.requires_approval,
        timeout_ms=30_000,
        max_retries=0,
        backoff_ms=200,
        idempotent=not binding.side_effect,
        side_effect=binding.side_effect,
    )


def _model_from_schema(spec: Mapping[str, Any]) -> type:
    """**JSON Schema → pydantic 模型** ✓（治理只需要形状 ✓ —— 宽松即可 ✓）。"""
    properties = spec.get("properties")
    fields: dict[str, Any] = {}
    if isinstance(properties, dict):
        for name in properties:
            fields[name] = (Any, None)
    return create_model("ToolArguments", **fields)


def _as_text(content: Any) -> str:
    """**消息内容 → 文本** ✓（多模态内容块取文本部分 ✓）。"""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(str(part.get("text") or "") for part in content if isinstance(part, dict))
    return str(content)


def _scope(*, call_id: str, turn_id: str | None, session_id: str | None, protected: bool):
    """**这一次工具调用的上下文** ✓（幂等键 ✓ / 轮次 ✓ / 是否受保护 ✓）。"""
    from ..execution.tool_binding import ToolScope

    return ToolScope(
        tool_call_id=call_id,
        idempotency_key=f"{turn_id}:{call_id}" if turn_id and call_id else None,
        turn_id=turn_id,
        session_id=session_id,
        protected=protected,
    )


__all__ = ["AgentLoopRunner", "BoundTool", "LoopEvent"]
