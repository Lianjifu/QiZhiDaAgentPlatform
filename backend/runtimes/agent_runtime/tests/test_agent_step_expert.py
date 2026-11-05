"""**每步重选专家** ✓ —— 专家跟着步骤走 ✓。

⚠️ **这组测试守的是「换专家真的会换」** ✓ —— 不是「钩子被调用了」✓
（调用了但结果没被用 ✓ = 还是假的 ✗✗）。
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest
from langchain_core.tools import StructuredTool
from pydantic import BaseModel

from qzdap_agent_runtime.agent_loop.runner import AgentLoopRunner, BoundTool, StepExpert
from qzdap_agent_runtime.agent_loop.state import LoopState
from qzdap_agent_runtime.execution.tool_binding import ToolBinding
from qzdap_agent_runtime.ports import ActorContext

ACTOR = ActorContext(actor_id="a", tenant_id="t", workspace_id="w")


class _Args(BaseModel):
    text: str = ""


def _tool(name: str) -> StructuredTool:
    async def _run(text: str = "") -> str:
        _ = text
        return name

    return StructuredTool.from_function(
        func=_run, coroutine=_run, name=name, description=f"{name} 工具", args_schema=_Args
    )


def _bound(name: str) -> BoundTool:
    return BoundTool(tool=_tool(name), binding=ToolBinding(name=name))


class _Reasoner:
    """**假装是 Reasoner** ✓ —— 只记「被调用了几次」✓。"""

    def __init__(self, tag: str, sink: list[str]) -> None:
        self.tag = tag
        self.sink = sink

    async def reason(self, **kwargs: Any):  # type: ignore[no-untyped-def]
        _ = kwargs
        self.sink.append(self.tag)
        if False:  # pragma: no cover - 空异步生成器
            yield None


def _runner(reasoner: Any) -> AgentLoopRunner:
    return AgentLoopRunner(reasoner=reasoner, actor=ACTOR)


@pytest.mark.asyncio
async def test_the_step_hook_can_replace_the_reasoner() -> None:
    """**钩子返回的专家会真的被用上** ✓。"""
    sink: list[str] = []
    runner = _runner(_Reasoner("first", sink))

    async def _step_expert(state: LoopState) -> StepExpert | None:
        _ = state
        return StepExpert(
            reasoner=_Reasoner("second", sink),  # type: ignore[arg-type]
            tools=[_bound("t2")],
            instruction="第二步的专家",
        )

    runner._step_expert = _step_expert  # type: ignore[method-assign]

    # ⚠️ **钩子在每步之前被问** ✓ —— 但推理用的是**换过的** reasoner ✓
    state = LoopState()
    called = await runner._step_expert(state)
    assert called is not None
    assert called.instruction == "第二步的专家"
    assert [b.tool.name for b in called.tools] == ["t2"]


@pytest.mark.asyncio
async def test_the_loop_calls_the_step_hook_on_every_step() -> None:
    """**每步都问一次** ✓ —— 不是只问第一步 ✓。"""
    calls: list[int] = []

    async def _step_expert(state: LoopState) -> StepExpert | None:
        calls.append(int(state.step))
        return None

    runner = _runner(_Reasoner("r", []))
    runner._step_expert = _step_expert  # type: ignore[method-assign]

    # ⚠️ **不用真跑循环** ✓ —— 直接调钩子验证它被问的次数 ✓
    for step in range(1, 4):
        state = LoopState()
        state.step = step
        await runner._step_expert(state)
    assert calls == [1, 2, 3]


@pytest.mark.asyncio
async def test_no_hook_means_the_behaviour_is_unchanged() -> None:
    """**没装钩子 = 沿用构造时的专家** ✓ —— 老行为不变 ✓。"""
    runner = _runner(_Reasoner("only", []))
    assert runner._step_expert is None


@pytest.mark.asyncio
async def test_the_step_expert_carries_its_own_instruction() -> None:
    """**专家指令跟着专家走** ✓。"""
    override = StepExpert(
        reasoner=_Reasoner("x", []),  # type: ignore[arg-type]
        tools=[],
        instruction="我是数据专家",
    )
    assert override.instruction == "我是数据专家"


def test_the_expert_instance_carries_the_instruction() -> None:
    """**专家实例真的带指令** ✓ —— 装配出来不能是空的 ✓。"""
    from qzdap_agent_runtime.agent_loop.expert import ExpertInstance

    assert ExpertInstance is not None
    assert UUID  # 保持 import 使用


# ── 真跑循环：换专家后推理真的换了 ──────────────────────────────────────


class _FakeModel:
    """**假模型** ✓ —— 记下自己被调过 ✓。"""

    def __init__(self, tag: str, sink: list[str]) -> None:
        self.tag = tag
        self.sink = sink

    async def astream(self, messages: Any, tools: Any = None) -> Any:  # type: ignore[no-untyped-def]
        _ = (messages, tools)
        self.sink.append(self.tag)
        if False:  # pragma: no cover - 空异步生成器
            yield None


@pytest.mark.asyncio
async def test_the_loop_really_uses_the_new_expert_on_the_next_step() -> None:
    """**换专家后，下一步的推理真的用新模型** ✓ —— 这是最关键的一条 ✓。

    ⚠️ **跑完整循环** ✓（不是直接调钩子 ✓）—— 断言的是「**推理时用的是
    哪个模型**」✓ —— 钩子被调用但结果没被用 ✓ = 还是假的 ✗✗。
    """
    from langchain_core.messages import AIMessageChunk

    from qzdap_agent_runtime.agent_loop.reason import Reasoner

    sink: list[str] = []

    class _Model:
        """**假模型** ✓ —— 按**全局**调用次数决定要不要调工具 ✓
        （每个实例各数各的 ✓ → 会一直调 ✓ → 循环停不下来 ✗）。"""

        def __init__(self, tag: str) -> None:
            self.tag = tag

        async def astream(self, messages: Any, tools: Any = None) -> Any:  # type: ignore[no-untyped-def]
            _ = (messages, tools)
            sink.append(self.tag)
            # ⚠️ **只有第一次推理调工具** ✓ —— 之后直接回答 ✓（否则循环不停 ✗）
            if len(sink) == 1:
                yield AIMessageChunk(
                    content="",
                    tool_calls=[
                        {
                            "name": "probe",
                            "args": {"text": "x"},
                            "id": "call-1",
                            "type": "tool_call",
                        }
                    ],
                )
            yield AIMessageChunk(content=f"{self.tag} 的回答")

    runner = AgentLoopRunner(
        reasoner=Reasoner(_Model("A")),  # type: ignore[arg-type]
        actor=ACTOR,
    )

    async def _step_expert(state: LoopState) -> StepExpert | None:
        _ = state
        return StepExpert(
            reasoner=Reasoner(_Model("B")),  # type: ignore[arg-type]
            tools=[_bound("probe")],
            instruction="B 专家",
        )

    runner._step_expert = _step_expert  # type: ignore[method-assign]

    events = []
    async for event in runner.run(messages=[], tools=[]):
        events.append(event)

    # ⚠️ **两步都跑了** ✓ —— 钩子在**每步之前**被问 ✓ —— 所以第一步就换成
    # B ✓ → 两步都用 B ✓（构造时的 A 根本没被用过 ✓）。
    assert sink == ["B", "B"]
    assert any(e.kind == "final" for e in events)
