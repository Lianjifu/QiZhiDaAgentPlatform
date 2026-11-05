"""**并行工具调用** ✓ —— 只读的并行 ✓，有副作用的串行 ✓。

⚠️ **这组测试守的是「顺序」与「隔离」** ✓ —— 并行最容易坏在这两处 ✓。
"""

from __future__ import annotations

import asyncio
from typing import Any, cast

import pytest
from langchain_core.tools import StructuredTool
from pydantic import BaseModel

from qzdap_agent_runtime.agent_loop.reason import Reasoner
from qzdap_agent_runtime.agent_loop.runner import AgentLoopRunner, BoundTool
from qzdap_agent_runtime.execution.tool_binding import ToolBinding
from qzdap_agent_runtime.ports import ActorContext

ACTOR = ActorContext(actor_id="a", tenant_id="t", workspace_id="w")


class _Args(BaseModel):
    text: str = ""


def _tool(name: str, log: list[str], delay: float = 0.0) -> StructuredTool:
    async def _run(text: str = "") -> str:
        log.append(f"start:{name}")
        if delay:
            await asyncio.sleep(delay)
        log.append(f"end:{name}")
        return f"{name}:{text}"

    return StructuredTool.from_function(
        func=_run,
        coroutine=_run,
        name=name,
        description=f"{name} 工具",
        args_schema=_Args,
    )


def _runner() -> AgentLoopRunner:
    """**一个不带 reasoner 能力的 runner** ✓ —— 这组测试只碰工具执行 ✓。"""
    return AgentLoopRunner(reasoner=Reasoner(model=cast(Any, None)), actor=ACTOR)


def _bound(
    name: str,
    log: list[str],
    *,
    side_effect: bool = False,
    risk: str = "low",
    requires_approval: bool = False,
    delay: float = 0.0,
) -> BoundTool:
    return BoundTool(
        tool=_tool(name, log, delay=delay),
        binding=ToolBinding(
            name=name,
            risk=risk,  # type: ignore[arg-type]
            side_effect=side_effect,
            requires_approval=requires_approval,
        ),
    )


@pytest.mark.asyncio
async def test_read_only_tools_run_in_parallel() -> None:
    """**只读工具并行** ✓ —— 快的不会被慢的拖住 ✓。"""
    log: list[str] = []
    runner = _runner()
    bound = _bound("read", log, delay=0.05)
    calls = [
        {"id": "c1", "name": "read", "args": {"text": "1"}},
        {"id": "c2", "name": "read", "args": {"text": "2"}},
    ]
    outcomes = await runner._invoke_all([(calls[0], bound), (calls[1], bound)])
    assert len(outcomes) == 2
    # ⚠️ **两个都先开始了** ✓ —— 串行的话第二个 start 会在第一个 end 之后 ✗
    assert log.index("start:read") == 0
    assert log.count("start:read") == 2
    assert log[1] == "start:read"


@pytest.mark.asyncio
async def test_tools_with_side_effects_run_serially() -> None:
    """**有副作用的工具串行** ✓ —— 顺序不能乱 ✗✗。"""
    log: list[str] = []
    runner = _runner()
    bound = _bound("write", log, side_effect=True)
    calls = [
        {"id": "c1", "name": "write", "args": {"text": "1"}},
        {"id": "c2", "name": "write", "args": {"text": "2"}},
    ]
    await runner._invoke_all([(calls[0], bound), (calls[1], bound)])
    # ⚠️ **严格 start/end 交替** ✓ —— 并行会是 start,start,end,end ✗
    assert log == [
        "start:write",
        "end:write",
        "start:write",
        "end:write",
    ]


@pytest.mark.asyncio
async def test_a_high_risk_tool_is_not_parallelised() -> None:
    """**高风险工具不并行** ✓ —— 出错时要能立刻停 ✗。"""
    log: list[str] = []
    runner = _runner()
    bound = _bound("risky", log, risk="high")
    calls = [
        {"id": "c1", "name": "risky", "args": {}},
        {"id": "c2", "name": "risky", "args": {}},
    ]
    await runner._invoke_all([(calls[0], bound), (calls[1], bound)])
    assert log == ["start:risky", "end:risky", "start:risky", "end:risky"]


@pytest.mark.asyncio
async def test_the_results_keep_the_request_order() -> None:
    """**结果按请求顺序** ✓ —— 模型读结果的顺序有意义 ✓。"""
    log: list[str] = []
    runner = _runner()
    fast = _bound("fast", log)
    slow = _bound("slow", log, delay=0.05)
    calls = [
        {"id": "c1", "name": "fast", "args": {"text": "1"}},
        {"id": "c2", "name": "slow", "args": {"text": "2"}},
    ]
    outcomes = await runner._invoke_all([(calls[0], fast), (calls[1], slow)])
    assert [o.tool_call_id for o in outcomes] == ["c1", "c2"]


@pytest.mark.asyncio
async def test_a_failing_parallel_tool_does_not_kill_the_batch() -> None:
    """**并发里一个工具炸了不带走整批** ✓ —— 与串行同口径 ✓。"""

    async def _boom(text: str = "") -> str:
        _ = text
        raise RuntimeError("工具内部炸了")

    bound = BoundTool(
        tool=StructuredTool.from_function(
            func=_boom,
            coroutine=_boom,
            name="boom",
            description="会炸的工具",
            args_schema=_Args,
        ),
        binding=ToolBinding(name="boom"),
    )
    runner = _runner()
    calls = [
        {"id": "c1", "name": "boom", "args": {}},
        {"id": "c2", "name": "boom", "args": {}},
    ]
    outcomes = await runner._invoke_all([(calls[0], bound), (calls[1], bound)])
    assert len(outcomes) == 2
    assert all(o.is_error for o in outcomes)
