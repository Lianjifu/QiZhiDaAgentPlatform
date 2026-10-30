"""Agent Stage 5：**整条循环** ✓（Agent 方案 §3 ✓ / §3.4 ✓）。

⚠️ **2026-10-15 那次重构失败在「没有一条测试跑完整个循环」** ✗✗ ——
所以这里**跑完整条循环** ✓（Reason → 工具 → Observe → Evaluate → 收尾 ✓）。

验收覆盖 ✓：整条循环 ✓ / 失败的工具也回灌 ✓ / **没有 actor 不许执行工具** ✓ /
审批挂起 ✓ / 治理拒绝 ✓ / 六个终止条件 ✓。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

import pytest
from langchain_core.messages import HumanMessage
from qzdap_agent_runtime.agent_loop.evaluate import BUDGET_EXCEEDED, Evaluator
from qzdap_agent_runtime.agent_loop.observe import Observer, ToolOutcome
from qzdap_agent_runtime.agent_loop.reason import Reasoner
from qzdap_agent_runtime.agent_loop.runner import AgentLoopRunner, BoundTool
from qzdap_agent_runtime.execution import QZDAPChatModel
from qzdap_agent_runtime.execution.tool_binding import ToolBindingResolver
from qzdap_agent_runtime.ports import (
    ActorContext,
    ToolBinding,
    ToolInvocation,
    ToolInvocationResult,
)

TENANT = uuid4()
WORKSPACE = uuid4()

_ACTOR = ActorContext(
    actor_id="user-1", tenant_id=str(TENANT), workspace_id=str(WORKSPACE)
)


class _ScriptedLLM:
    """按脚本产出 chunk 的端口替身 ✓。"""

    def __init__(self, scripts: list[list[dict[str, Any]]]) -> None:
        self._scripts = scripts
        self.calls = 0

    async def stream(
        self, request: Any, **kwargs: Any
    ) -> AsyncIterator[Any]:  # pragma: no cover
        from qzdap_llm.client import LLMChunk

        script = self._scripts[min(self.calls, len(self._scripts) - 1)]
        self.calls += 1
        for raw in script:
            yield LLMChunk(**raw)


class _Runtime:
    """工具执行端口的替身 ✓。"""

    def __init__(self, *, ok: bool = True, output: str = "ok") -> None:
        self._ok = ok
        self._output = output
        self.calls: list[ToolInvocation] = []

    async def invoke(
        self, invocation: ToolInvocation, *, actor: ActorContext
    ) -> ToolInvocationResult:
        self.calls.append(invocation)
        if not self._ok:
            return ToolInvocationResult(
                ok=False,
                error_code="TOOL_FAILED",
                error_message="工具炸了",
                is_error=True,
            )
        return ToolInvocationResult(ok=True, output=self._output)


_ECHO = ToolBinding(
    name="echo",
    kind="tool",
    risk="low",
    spec={
        "description": "回显",
        "parameters": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
        },
    },
)
_WRITE = ToolBinding(
    name="write_file",
    kind="tool",
    risk="high",
    requires_approval=True,
    side_effect=True,
    spec={
        "description": "写文件",
        "parameters": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
        },
    },
)


class _Harness:
    """**循环 + 工具 + 脚本** ✓（测试要的那些零件 ✓）。"""

    def __init__(
        self,
        scripts: list[list[dict[str, Any]]],
        *,
        bindings: list[ToolBinding] | None = None,
        runtime: _Runtime | None = None,
        actor: ActorContext | None = _ACTOR,
        evaluator: Evaluator | None = None,
        policy_guard: Any | None = None,
        cost_of: Any | None = None,
    ) -> None:
        llm = _ScriptedLLM(scripts)
        reasoner = Reasoner(QZDAPChatModel(llm=llm, model_name="demo"))  # type: ignore[arg-type]
        self.runtime = runtime or _Runtime()
        resolver = ToolBindingResolver(self.runtime)
        self.tools = [
            BoundTool(tool=resolver.resolve([binding])[0], binding=binding)
            for binding in (bindings or [])
        ]
        self.runner = AgentLoopRunner(
            reasoner=reasoner,
            evaluator=evaluator or Evaluator(max_steps=4),
            observer=Observer(),
            policy_guard=policy_guard,
            actor=actor,
            turn_id="turn-1",
            cost_of=cost_of,
        )

    async def run(self, **kwargs: Any) -> list[Any]:
        return [
            event
            async for event in self.runner.run(
                messages=[HumanMessage(content="嗨")], tools=self.tools, **kwargs
            )
        ]


def _call(call_id: str, name: str, arguments: str) -> dict[str, Any]:
    """**平台侧的工具调用 delta** ✓（形状 = ``LLMChunk.tool_calls`` ✓）。"""
    return {"id": call_id, "index": 0, "name": name, "arguments": arguments}


class TestTheWholeLoop:
    @pytest.mark.asyncio
    async def test_the_tool_result_goes_back_and_the_loop_finishes(self) -> None:
        """**整条循环** ✓（工具 → 回灌 → 最终回答 ✓）。"""
        harness = _Harness(
            [
                [{"model": "demo", "delta": "", "tool_calls": [_call("call-1", "echo", '{"text":"hi"}')]}],
                [{"model": "demo", "delta": "回答"}],
            ],
            bindings=[_ECHO],
        )
        events = await harness.run()
        kinds = [event.kind for event in events]
        assert "tool_call" in kinds
        assert "tool_result" in kinds
        assert kinds[-1] == "final"
        assert events[-1].text == "回答"
        # ⚠️ **工具真的执行了** ✓（不是空转 ✓）
        assert len(harness.runtime.calls) == 1
        assert harness.runtime.calls[0].arguments == {"text": "hi"}
        # ⚠️ **幂等键带上了轮次** ✓
        assert harness.runtime.calls[0].idempotency_key == "turn-1:call-1"

    @pytest.mark.asyncio
    async def test_the_failing_tool_is_reported_back(self) -> None:
        """**失败的工具也要回灌** ✓（§3.2 规则 1 ✓）。"""
        harness = _Harness(
            [
                [{"model": "demo", "delta": "", "tool_calls": [_call("call-1", "echo", "{}")]}],
                [{"model": "demo", "delta": "换个说法"}],
            ],
            bindings=[_ECHO],
            runtime=_Runtime(ok=False),
        )
        events = await harness.run()
        results = [event for event in events if event.kind == "tool_result"]
        assert results and results[0].tool_result is not None
        assert results[0].tool_result["is_error"] is True
        # ⚠️ **失败之后循环继续** ✓（模型还有机会换策略 ✓）
        assert events[-1].kind == "final"

    @pytest.mark.asyncio
    async def test_the_tool_which_is_not_bound_is_reported_back(self) -> None:
        """**没绑定的工具也要回灌** ✓（不能静默吞掉 ✓）。"""
        harness = _Harness(
            [
                [{"model": "demo", "delta": "", "tool_calls": [_call("call-1", "ghost", "{}")]}],
                [{"model": "demo", "delta": "结束"}],
            ],
            bindings=[_ECHO],
        )
        events = await harness.run()
        results = [event for event in events if event.kind == "tool_result"]
        assert results and results[0].tool_result is not None
        assert results[0].tool_result["is_error"] is True
        assert "没有绑定" in str(results[0].tool_result["output"])
        assert not harness.runtime.calls

    @pytest.mark.asyncio
    async def test_without_a_real_actor_the_tool_is_not_executed(self) -> None:
        """**没有真实调用者就不许执行工具** ✓（§3.5 的洞 ✓）。"""
        harness = _Harness(
            [
                [{"model": "demo", "delta": "", "tool_calls": [_call("call-1", "echo", '{"text":"hi"}')]}],
                [{"model": "demo", "delta": "结束"}],
            ],
            bindings=[_ECHO],
            actor=None,
        )
        events = await harness.run()
        results = [event for event in events if event.kind == "tool_result"]
        assert results and results[0].tool_result is not None
        assert results[0].tool_result["is_error"] is True
        assert "调用者" in str(results[0].tool_result["output"])
        # ⚠️ **工具根本没被调到** ✓
        assert not harness.runtime.calls


class TestGovernance:
    @pytest.mark.asyncio
    async def test_the_approval_tool_suspends_the_loop(self) -> None:
        """**审批挂起 → suspend** ✓（§3.5 ✓）—— **不执行** ✓。"""
        harness = _Harness(
            [
                [{"model": "demo", "delta": "", "tool_calls": [_call("call-1", "write_file", '{"path":"a.txt"}')]}]
            ],
            bindings=[_WRITE],
        )
        events = await harness.run()
        approvals = [event for event in events if event.kind == "approval_required"]
        assert approvals, [event.kind for event in events]
        assert approvals[0].approval is not None
        assert approvals[0].approval["tool_name"] == "write_file"
        assert approvals[0].approval["request_hash"]
        assert not [event for event in events if event.kind == "tool_result"]
        assert not harness.runtime.calls

    @pytest.mark.asyncio
    async def test_the_policy_guard_can_deny_the_tool(self) -> None:
        """**治理拒绝 → 明确错误** ✓（不执行 ✓）。"""

        class _Deny:
            async def decide(self, **_kwargs: Any):
                return "deny", "策略不允许"

        harness = _Harness(
            [
                [{"model": "demo", "delta": "", "tool_calls": [_call("call-1", "write_file", '{"path":"a.txt"}')]}]
            ],
            bindings=[_WRITE],
            policy_guard=_Deny(),
        )
        events = await harness.run()
        errors = [event for event in events if event.kind == "error"]
        assert errors and errors[0].error_code == "TOOL_DENIED"
        assert not harness.runtime.calls

    @pytest.mark.asyncio
    async def test_the_policy_guard_can_approve_the_tool(self) -> None:
        """**治理放行 → 工具执行** ✓（治理是默认路径 ✓）。"""

        class _Allow:
            async def decide(self, **_kwargs: Any):
                return "allow", None

        harness = _Harness(
            [
                [{"model": "demo", "delta": "", "tool_calls": [_call("call-1", "write_file", '{"path":"a.txt"}')]}],
                [{"model": "demo", "delta": "写好了"}],
            ],
            bindings=[_WRITE],
            policy_guard=_Allow(),
        )
        events = await harness.run()
        assert [event for event in events if event.kind == "approval_required"] == []
        assert len(harness.runtime.calls) == 1
        assert events[-1].kind == "final"


class TestTermination:
    @pytest.mark.asyncio
    async def test_the_step_budget_aborts(self) -> None:
        """**步数闸门** ✓（§3.4 条件 1 ✓）。"""
        harness = _Harness(
            [
                [{"model": "demo", "delta": "", "tool_calls": [_call("call-1", "echo", '{"text":"x"}')]}]
            ],
            bindings=[_ECHO],
            evaluator=Evaluator(max_steps=1),
        )
        events = await harness.run()
        errors = [event for event in events if event.kind == "error"]
        assert errors and errors[0].error_code == BUDGET_EXCEEDED

    @pytest.mark.asyncio
    async def test_the_cost_budget_aborts(self) -> None:
        """**成本闸门** ✓（§3.4 条件 2 ✓ —— 决策 #7 的轮次级硬闸门 ✓）。"""
        from qzdap_llm.client import Usage

        harness = _Harness(
            [
                [
                    {
                        "model": "demo",
                        "delta": "回答",
                        "usage": Usage(input_tokens=1000, output_tokens=1000),
                    }
                ]
            ],
            evaluator=Evaluator(max_steps=4, max_cost_usd=0.0001),
            cost_of=lambda _i, _o: 1.0,
        )
        events = await harness.run()
        errors = [event for event in events if event.kind == "error"]
        assert errors and errors[0].error_code == BUDGET_EXCEEDED

    @pytest.mark.asyncio
    async def test_the_cancel_stops_the_loop(self) -> None:
        """**用户取消** ✓（§3.4 条件 4 ✓）。"""
        harness = _Harness(
            [[{"model": "demo", "delta": "回答"}]],
            evaluator=Evaluator(max_steps=4),
        )
        events = await harness.run(cancelled=lambda: True)
        errors = [event for event in events if event.kind == "error"]
        assert errors and errors[0].error_code == "TURN_CANCELLED"

    @pytest.mark.asyncio
    async def test_the_stall_guard_stops_the_loop(self) -> None:
        """**空转护栏** ✓（§3.4 条件 6 ✓ —— 同样的工具反复调 → 收尾 ✓）。"""
        harness = _Harness(
            [
                [{"model": "demo", "delta": "", "tool_calls": [_call("call-1", "echo", '{"text":"x"}')]}]
            ],
            bindings=[_ECHO],
            evaluator=Evaluator(max_steps=8, stall_limit=2),
        )
        events = await harness.run()
        kinds = [event.kind for event in events]
        assert kinds.count("tool_result") >= 2
        assert kinds[-1] == "final"


class TestObserver:
    def test_the_failed_result_is_marked_as_an_error(self) -> None:
        """**失败的结果标成 error** ✓（§3.2 规则 1 ✓）。"""
        observer = Observer()
        messages = observer.messages(
            [
                ToolOutcome(tool_call_id="c1", name="echo", output="ok"),
                ToolOutcome(tool_call_id="c2", name="echo", output="炸了", is_error=True),
            ]
        )
        assert messages[0].status == "success"
        assert messages[1].status == "error"
        assert messages[0].tool_call_id == "c1"

    def test_the_output_is_truncated(self) -> None:
        """**兜底截断** ✓（§3.2 规则 2 ✓）。"""
        observer = Observer(max_output_chars=10)
        message = observer.messages(
            [ToolOutcome(tool_call_id="c1", name="echo", output="x" * 100)]
        )[0]
        assert len(str(message.content)) <= 20
