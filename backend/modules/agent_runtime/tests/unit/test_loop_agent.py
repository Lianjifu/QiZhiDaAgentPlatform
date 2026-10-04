"""Bounded ReAct loop + compact + memory write tests."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest
from qzdap_llm.client import ChatRequest, LLMChunk, Usage
from qzdap_schema.dtos.turn import ApprovalRequiredChunk, ContextCompactedChunk, DoneChunk, MemoryWriteChunk

from qzdap.modules.agent_runtime.adapter.graph.compact import compact_messages
from qzdap.modules.agent_runtime.adapter.graph.loop import HARD_MAX_STEPS, apply_stall_guard, next_route
from qzdap.modules.agent_runtime.adapter.graph.runner import SessionGraphRunner
from qzdap.modules.agent_runtime.application.ports import LLMPort
from qzdap.modules.agent_runtime.domain.catalog import CatalogAgent

TENANT = UUID("00000000-0000-0000-0000-000000000001")
WORKSPACE = UUID("00000000-0000-0000-0000-000000000002")
OWNER = UUID("00000000-0000-0000-0000-000000000010")


class ScriptedLLM(LLMPort):
    def __init__(self, steps: list[dict[str, Any]]) -> None:
        self._steps = list(steps)
        self.calls = 0

    async def stream(self, req: ChatRequest, **kwargs: object):
        _ = kwargs
        idx = min(self.calls, len(self._steps) - 1)
        self.calls += 1
        step = self._steps[idx]
        if step.get("delta"):
            yield LLMChunk(model=req.model, delta=str(step["delta"]))
        if step.get("tool_calls"):
            yield LLMChunk(model=req.model, delta="", tool_calls=list(step["tool_calls"]))
        yield LLMChunk(
            model=req.model,
            delta="",
            finish_reason="stop",
            usage=Usage(input_tokens=4, output_tokens=2),
        )


class RecordingMemory:
    def __init__(self) -> None:
        self.writes: list[str] = []
        self.facts: list[str] = []

    async def recall(self, **kwargs: object) -> list[dict]:
        _ = kwargs
        return [{"id": "m1", "content": fact, "score": 0.9} for fact in self.facts]

    async def write(self, **kwargs: object) -> dict:
        content = str(kwargs.get("content") or "")
        self.writes.append(content)
        self.facts.append(content)
        return {"ok": True}


class ConfirmSkill:
    async def list_executable(self) -> list[dict]:
        return [{"name": "wipe_disk", "needConfirm": True, "risk": "high", "description": "wipe"}]

    async def invoke(self, **kwargs: object) -> dict:
        if not kwargs.get("confirmed"):
            return {"ok": False, "error_code": "SKILL_NEEDS_CONFIRM"}
        return {"ok": True, "output": "wiped"}


def _agent(**overrides: object) -> CatalogAgent:
    data = dict(
        id=uuid4(),
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        name="助手",
        category="企业通用",
        owner="管理员",
        description="",
        model="demo",
    )
    data.update(overrides)
    return CatalogAgent.create(**data)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_loop_chains_tool_calls_then_finishes() -> None:
    llm = ScriptedLLM(
        [
            {
                "tool_calls": [
                    {"id": str(uuid4()), "name": "lookup", "arguments": {"q": "a"}},
                ]
            },
            {"delta": "根据工具结果，答案是 42。"},
        ]
    )

    class LookupSkill:
        async def list_executable(self) -> list[dict]:
            return [{"name": "lookup", "needConfirm": False, "risk": "low"}]

        async def invoke(self, **kwargs: object) -> dict:
            return {"ok": True, "output": "42"}

    runner = SessionGraphRunner(llm=llm, skill_port=LookupSkill())  # type: ignore[arg-type]
    chunks = []
    async for chunk in runner.run_turn(
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        owner_id=OWNER,
        turn_id=uuid4(),
        user_input="多少？",
        history=[],
        agent=_agent(),
        model="demo",
    ):
        chunks.append(chunk)
    assert any(getattr(c, "kind", None) == "tool_result" for c in chunks)
    assert isinstance(chunks[-1], DoneChunk)
    assert "42" in (chunks[-1].final_message or "")


@pytest.mark.asyncio
async def test_max_steps_stops() -> None:
    llm = ScriptedLLM(
        [
            {
                "tool_calls": [
                    {"id": str(uuid4()), "name": "lookup", "arguments": {"q": i}},
                ]
            }
            for i in range(20)
        ]
    )

    class LookupSkill:
        async def list_executable(self) -> list[dict]:
            return [{"name": "lookup", "needConfirm": False, "risk": "low"}]

        async def invoke(self, **kwargs: object) -> dict:
            return {"ok": True, "output": "x"}

    agent = _agent()
    from dataclasses import replace

    agent = replace(agent, max_steps=2)
    runner = SessionGraphRunner(llm=llm, skill_port=LookupSkill())  # type: ignore[arg-type]
    kinds = []
    async for chunk in runner.run_turn(
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        owner_id=OWNER,
        turn_id=uuid4(),
        user_input="转圈",
        history=[],
        agent=agent,
        model="demo",
    ):
        kinds.append(chunk.kind)
    assert kinds[-1] == "done"
    assert llm.calls <= HARD_MAX_STEPS
    assert llm.calls <= 3


def test_stall_guard_breaks_identical_tools() -> None:
    call = {"name": "lookup", "arguments": {"q": "same"}}
    state = {"messages": [], "last_tool_sig": "", "stall_count": 0}
    state = apply_stall_guard(state, [call])  # type: ignore[arg-type]
    state = apply_stall_guard(state, [call])  # type: ignore[arg-type]
    state = apply_stall_guard(state, [call])  # type: ignore[arg-type]
    assert state["stall_count"] >= 2
    assert any(m.get("role") == "system" for m in state["messages"])
    assert next_route({"messages": [{"role": "assistant", "content": "ok"}], "step": 1, "max_steps": 8}) == "end"


@pytest.mark.asyncio
async def test_high_risk_emits_approval_and_resume_executes() -> None:
    call_id = str(uuid4())
    llm = ScriptedLLM(
        [
            {"tool_calls": [{"id": call_id, "name": "wipe_disk", "arguments": {"path": "/"}}]},
            {"delta": "已完成。"},
        ]
    )
    runner = SessionGraphRunner(llm=llm, skill_port=ConfirmSkill())  # type: ignore[arg-type]
    first = []
    async for chunk in runner.run_turn(
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        owner_id=OWNER,
        turn_id=uuid4(),
        user_input="清理磁盘",
        history=[],
        agent=_agent(),
        model="demo",
    ):
        first.append(chunk)
    assert isinstance(first[-1], ApprovalRequiredChunk)
    pending = dict(runner.last_loop_state.get("pending_approval") or {})
    pending["decision"] = "approved"
    second = []
    async for chunk in runner.run_turn(
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        owner_id=OWNER,
        turn_id=uuid4(),
        user_input="继续",
        history=[],
        agent=_agent(),
        model="demo",
        resume={**runner.last_loop_state, "pending_approval": pending, "decision": "approved"},
    ):
        second.append(chunk)
    assert any(getattr(c, "kind", None) == "tool_result" for c in second)
    assert isinstance(second[-1], DoneChunk)


@pytest.mark.asyncio
async def test_memory_write_and_second_turn_recall() -> None:
    memory = RecordingMemory()
    llm = ScriptedLLM([{"delta": "客户叫张三。"}])
    runner = SessionGraphRunner(llm=llm, memory_port=memory)  # type: ignore[arg-type]
    async for _chunk in runner.run_turn(
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        owner_id=OWNER,
        turn_id=uuid4(),
        user_input="记住客户叫张三",
        history=[],
        agent=_agent(),
        model="demo",
    ):
        if isinstance(_chunk, MemoryWriteChunk):
            assert _chunk.layer in {"l1", "l2"}
    assert memory.writes
    llm2 = ScriptedLLM([{"delta": "客户是张三。"}])
    runner2 = SessionGraphRunner(llm=llm2, memory_port=memory)  # type: ignore[arg-type]
    texts = []
    async for chunk in runner2.run_turn(
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        owner_id=OWNER,
        turn_id=uuid4(),
        user_input="客户叫什么",
        history=[],
        agent=_agent(),
        model="demo",
    ):
        if getattr(chunk, "kind", None) == "message":
            texts.append(chunk.content)
    assert any("张三" in t for t in texts) or memory.facts


def test_compact_emits_when_over_budget() -> None:
    history = [{"role": "user", "content": "x" * 800} for _ in range(40)]
    history.append({"role": "assistant", "content": "ok"})
    compacted, summary, did = compact_messages(history, context_window=2000)
    assert did is True
    assert summary
    assert len(compacted) < len(history)


@pytest.mark.asyncio
async def test_compact_chunk_on_long_history() -> None:
    llm = ScriptedLLM([{"delta": "好的"}])
    runner = SessionGraphRunner(llm=llm)
    history = [{"role": "user", "content": "y" * 400} for _ in range(30)]
    kinds = []
    async for chunk in runner.run_turn(
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        owner_id=OWNER,
        turn_id=uuid4(),
        user_input="总结",
        history=history,
        agent=_agent(),
        model="demo",
        context_window=2000,
    ):
        kinds.append(chunk.kind)
    assert "context_compacted" in kinds
    assert isinstance(ContextCompactedChunk(turn_id=uuid4(), seq=1, tokens_before=1, tokens_after=1), ContextCompactedChunk)
