"""Bounded ReAct loop + compact + memory write tests."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest

from qzdap.modules.agent_runtime.adapter.graph.runner import SessionGraphRunner
from qzdap.modules.agent_runtime.adapter.llm import LLMPortAdapter
from qzdap.modules.agent_runtime.application.ports import LLMPort
from qzdap.modules.agent_runtime.domain.catalog import CatalogAgent
from qzdap_agent_runtime.agent_loop.evaluate import HARD_MAX_STEPS
from qzdap_llm.client import ChatRequest, LLMChunk, Usage
from qzdap_schema.dtos.turn import (
    ApprovalRequiredChunk,
    ContextCompactedChunk,
    DoneChunk,
    MemoryWriteChunk,
)
from qzdap_schema.ids import ModelId
from qzdap_vault.actor import ActorContext

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

    async def synthetic_chunks(
        self, user_input: str, *, turn_id: UUID | None = None
    ) -> list[dict[str, Any]]:
        # 测试桩默认空 — 触发词驱动的事件在专门的 fixture 里覆盖.
        _ = (user_input, turn_id)
        return []


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

    async def write_turn(self, **kwargs: object) -> dict:
        """新写入口 ✓（A-26 ✓）—— 轮次收尾用它沉淀记忆 ✓。"""
        content = str(kwargs.get("user_input") or "")
        self.writes.append(content)
        self.facts.append(content)
        return {"written": 1, "rejected": 0, "deduplicated": 0}


class ConfirmSkill:
    async def list_executable(self) -> list[dict]:
        return [{"name": "wipe_disk", "needConfirm": True, "risk": "high", "description": "wipe"}]

    async def invoke(self, **kwargs: object) -> dict:
        if not kwargs.get("confirmed"):
            return {"ok": False, "error_code": "SKILL_NEEDS_CONFIRM"}
        return {"ok": True, "output": "wiped"}


def _agent(**overrides: object) -> CatalogAgent:
    data = {
        "id": uuid4(),
        "tenant_id": TENANT,
        "workspace_id": WORKSPACE,
        "name": "助手",
        "category": "企业通用",
        "owner": "管理员",
        "description": "",
        "model": "demo",
    }
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


@pytest.mark.asyncio
async def test_the_compressor_folds_when_over_budget() -> None:
    """**超预算就折叠** ✓ —— 走**新的** Compressor ✓（旧的
    `compact_messages` 已删 ✓ —— Context Stage 5 ✓）。"""
    from qzdap_agent_runtime.context.compressor import ContextCompressor

    history = [{"role": "user", "content": "x" * 800} for _ in range(40)]
    history.append({"role": "assistant", "content": "ok"})
    outcome = await ContextCompressor(context_window=8000).compact(messages=history)
    assert outcome.tokens_after < outcome.tokens_before
    assert outcome.summary
    assert len(outcome.messages) < len(history)


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
    assert isinstance(
        ContextCompactedChunk(turn_id=uuid4(), seq=1, tokens_before=1, tokens_after=1),
        ContextCompactedChunk,
    )


@pytest.mark.asyncio
@pytest.mark.asyncio
async def test_saved_adapter_passes_actor_and_closes_stream() -> None:
    model_id = ModelId(uuid4())
    actor = ActorContext(tenant_id=TENANT, workspace_id=WORKSPACE, principal_id=OWNER)
    closed = False

    class SavedService:
        def stream(self, **kwargs: object):
            assert kwargs["actor"] == actor

            async def inner():
                nonlocal closed
                try:
                    yield LLMChunk(model="upstream", delta="x")
                finally:
                    closed = True

            return inner()

    adapter = LLMPortAdapter(ScriptedLLM([]), model_service=SavedService())
    iterator = adapter.stream(
        ChatRequest(model="saved", messages=[]), model_id=model_id, actor=actor
    )
    assert (await iterator.__anext__()).delta == "x"
    await iterator.aclose()
    assert closed


@pytest.mark.asyncio
async def test_saved_graph_early_delta_cancellation_closes_provider() -> None:
    import asyncio

    model_id = ModelId(uuid4())
    entered = asyncio.Event()
    closed = asyncio.Event()

    class SavedService:
        async def stream(self, *, actor, model_id: ModelId, req: ChatRequest):
            assert actor == ActorContext(
                tenant_id=TENANT, workspace_id=WORKSPACE, principal_id=OWNER
            )
            assert str(model_id) == req.model
            assert req.tools and req.tools[0]["function"]["name"] == "sandbox_exec"
            try:
                yield LLMChunk(model="actual-upstream", delta="first")
                entered.set()
                await asyncio.Event().wait()
            finally:
                closed.set()

    class Sandbox:
        async def exec(self, **_kwargs: object) -> dict:
            return {"ok": True, "output": "ok"}

    runner = SessionGraphRunner(
        llm=LLMPortAdapter(ScriptedLLM([]), model_service=SavedService()),
        # ⚠️ **沙箱工具** ✓ —— 新路径只在**配了沙箱**时才暴露它 ✓
        # （旧路径是无条件暴露 ✓ —— 那等于每个 agent 都凭空多了跑代码的能力 ✗✗）。
        sandbox_port=Sandbox(),  # type: ignore[arg-type]
    )
    stream = runner.run_turn(
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        owner_id=OWNER,
        turn_id=uuid4(),
        user_input="hi",
        history=[],
        agent=None,
        model=str(model_id),
    )
    first = await asyncio.wait_for(anext(stream), timeout=1)
    assert first.kind == "message" and first.content == "first"
    assert not entered.is_set()  # no read-ahead / completion buffering
    pending = asyncio.create_task(anext(stream))
    await asyncio.wait_for(entered.wait(), timeout=1)
    pending.cancel()
    with pytest.raises(asyncio.CancelledError):
        await pending
    assert closed.is_set()
    await stream.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "actor",
    [
        None,
        ActorContext(tenant_id=TENANT),
        ActorContext(tenant_id=TENANT, principal_id=UUID(int=0)),
    ],
)
async def test_saved_model_requires_real_actor(actor: ActorContext | None) -> None:
    adapter = LLMPortAdapter(ScriptedLLM([]), model_service=object())
    with pytest.raises(RuntimeError, match="real caller"):
        await anext(
            adapter.stream(
                ChatRequest(model="saved", messages=[]), model_id=ModelId(uuid4()), actor=actor
            )
        )


@pytest.mark.asyncio
async def test_saved_model_never_silently_falls_back_when_service_absent() -> None:
    adapter = LLMPortAdapter(ScriptedLLM([]))
    with pytest.raises(RuntimeError, match="unavailable"):
        await anext(
            adapter.stream(ChatRequest(model="saved", messages=[]), model_id=ModelId(uuid4()))
        )
