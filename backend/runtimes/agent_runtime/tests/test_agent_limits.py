"""**循环的三道闸门** ✓ —— 单步超时 ✓ / 工具配额 ✓ / 会话级成本 ✓。

⚠️ **还有一条韧性** ✓ —— 模型调用失败**不当场判死** ✓（吐过东西 ✓ → 就地
收尾 ✓；一个都没吐 ✓ → 照旧抛出去 ✓ —— HTTP 层要能用状态码表达失败 ✓）。
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

import pytest
from langchain_core.messages import HumanMessage

from qzdap_agent_runtime.agent_loop.evaluate import BUDGET_EXCEEDED, Evaluator
from qzdap_agent_runtime.agent_loop.observe import Observer
from qzdap_agent_runtime.agent_loop.reason import Reasoner
from qzdap_agent_runtime.agent_loop.runner import AgentLoopRunner
from qzdap_agent_runtime.execution import QZDAPChatModel
from qzdap_agent_runtime.ports import ActorContext, ToolBinding
from qzdap_kernel.error_codes import ErrorCode

TENANT = uuid4()
WORKSPACE = uuid4()

_ACTOR = ActorContext(actor_id="user-1", tenant_id=str(TENANT), workspace_id=str(WORKSPACE))

_ECHO = ToolBinding(
    name="echo",
    kind="tool",
    risk="low",
    spec={
        "description": "回显",
        "parameters": {"type": "object", "properties": {"text": {"type": "string"}}},
    },
)


def _call(call_id: str, name: str, arguments: str) -> dict[str, Any]:
    return {"id": call_id, "index": 0, "name": name, "arguments": arguments}


def _usage() -> Any:
    from qzdap_llm.client import Usage

    return Usage(input_tokens=10, output_tokens=5)


_USAGE = _usage()


class _HangingLLM:
    """**一个片都不吐的模型** ✓（上游挂住 ✓）。"""

    async def stream(self, request: Any, **kwargs: Any) -> AsyncIterator[Any]:  # pragma: no cover
        await asyncio.sleep(3600)
        yield  # pragma: no cover


class _BoomAfterTextLLM:
    """**吐了半句就炸** ✓（中途断 ✓）。"""

    async def stream(self, request: Any, **kwargs: Any) -> AsyncIterator[Any]:
        from qzdap_llm.client import LLMChunk

        yield LLMChunk(model="demo", delta="半句")
        raise RuntimeError("upstream exploded")


class _BoomLLM:
    """**一开始就炸** ✓。"""

    async def stream(self, request: Any, **kwargs: Any) -> AsyncIterator[Any]:
        raise RuntimeError("no provider")
        yield  # pragma: no cover


class _ScriptedLLM:
    def __init__(self, scripts: list[list[dict[str, Any]]]) -> None:
        self._scripts = scripts
        self.calls = 0

    async def stream(self, request: Any, **kwargs: Any) -> AsyncIterator[Any]:
        from qzdap_llm.client import LLMChunk

        script = self._scripts[min(self.calls, len(self._scripts) - 1)]
        self.calls += 1
        for raw in script:
            yield LLMChunk(**raw)


class _Runtime:
    async def invoke(self, invocation: Any, *, actor: ActorContext) -> Any:
        from qzdap_agent_runtime.ports import ToolInvocationResult

        return ToolInvocationResult(ok=True, output="ok")


def _runner(
    llm: Any,
    *,
    evaluator: Evaluator | None = None,
    step_timeout_seconds: float = 0.0,
    cost_of: Any = None,
) -> AgentLoopRunner:
    reasoner = Reasoner(QZDAPChatModel(llm=llm, model_name="demo"))  # type: ignore[arg-type]
    return AgentLoopRunner(
        reasoner=reasoner,
        evaluator=evaluator or Evaluator(max_steps=4),
        observer=Observer(),
        actor=_ACTOR,
        turn_id="turn-1",
        cost_of=cost_of,
        step_timeout_seconds=step_timeout_seconds,
    )


async def _run(runner: AgentLoopRunner) -> list[Any]:
    return [event async for event in runner.run(messages=[HumanMessage(content="嗨")], tools=[])]


class TestStepTimeout:
    @pytest.mark.asyncio
    async def test_a_hanging_model_is_cut_off(self) -> None:
        runner = _runner(_HangingLLM(), step_timeout_seconds=0.05)
        events = await _run(runner)
        errors = [event for event in events if event.kind == "error"]
        assert errors, "挂住的模型必须被掐断"
        assert errors[0].error_code == ErrorCode.AGENT_STEP_TIMEOUT.value


class TestToolQuota:
    @pytest.mark.asyncio
    async def test_too_many_tool_calls_abort_the_turn(self) -> None:
        llm = _ScriptedLLM(
            [
                [
                    {
                        "model": "demo",
                        "delta": "",
                        "tool_calls": [
                            _call("call-1", "echo", "{}"),
                            _call("call-2", "echo", "{}"),
                            _call("call-3", "echo", "{}"),
                        ],
                    }
                ]
            ]
        )
        runner = _runner(llm, evaluator=Evaluator(max_steps=4, max_tool_calls=2))
        events = await _run(runner)
        errors = [event for event in events if event.kind == "error"]
        assert errors
        assert errors[0].error_code == ErrorCode.AGENT_TOOL_QUOTA_EXCEEDED.value


class TestSessionCost:
    @pytest.mark.asyncio
    async def test_the_previous_turns_cost_counts_against_the_budget(self) -> None:
        """⚠️ **预算不再每轮重置** ✓ —— 会话累计 ✓。"""
        llm = _ScriptedLLM([[{"model": "demo", "delta": "回答", "usage": _USAGE}]])
        runner = _runner(
            llm,
            evaluator=Evaluator(max_steps=4, max_cost_usd=1.0, base_cost_usd=0.95),
            cost_of=lambda _in_tokens, _out_tokens: 0.2,
        )
        events = await _run(runner)
        errors = [event for event in events if event.kind == "error"]
        assert errors
        assert errors[0].error_code == BUDGET_EXCEEDED

    @pytest.mark.asyncio
    async def test_a_fresh_session_is_not_blocked_by_the_budget(self) -> None:
        llm = _ScriptedLLM([[{"model": "demo", "delta": "回答", "usage": _USAGE}]])
        runner = _runner(
            llm,
            evaluator=Evaluator(max_steps=4, max_cost_usd=1.0, base_cost_usd=0.0),
            cost_of=lambda _in_tokens, _out_tokens: 0.2,
        )
        events = await _run(runner)
        assert not [event for event in events if event.kind == "error"]


class TestLLMFailureResilience:
    @pytest.mark.asyncio
    async def test_a_failure_after_some_output_does_not_kill_the_turn(self) -> None:
        runner = _runner(_BoomAfterTextLLM())
        events = await _run(runner)
        texts = [event.text for event in events if event.kind == "text"]
        errors = [event for event in events if event.kind == "error"]
        assert texts == ["半句"]
        assert errors
        assert errors[0].error_code == ErrorCode.LLM_CALL_FAILED.value

    @pytest.mark.asyncio
    async def test_a_failure_before_any_output_is_still_raised(self) -> None:
        """⚠️ **一个 chunk 都没吐** ✓ → 抛出去 ✓ —— HTTP 层要能用状态码 ✓。"""
        runner = _runner(_BoomLLM())
        with pytest.raises(RuntimeError):
            await _run(runner)
