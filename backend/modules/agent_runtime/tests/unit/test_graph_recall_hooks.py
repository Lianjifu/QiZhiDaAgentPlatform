"""召回钩子（memory / knowledge）—— **现行实现**是 graph runner ✓。

⚠️ 旧的两份用例（``test_memory_recall_hook.py`` / ``test_knowledge_recall_hook.py``）
测的是**已删的第二套 turn 实现**（``RunTurnUseCase`` 里的召回 ✓）—— 随那一套
一起删（Session Stage 5b ✓）。

这里覆盖**同一条链上的现行实现**：``SessionGraphRunner`` 的上下文装配 ——
web / IM / 子代理 / 评估**都走它** ✓。要守住的行为有两个：

1. 召回**按用户**过滤（``user_id``）—— 漏了就会把同工作区别人的记忆召回来 ✗；
2. 召回**失败不炸这一轮** —— 降级成裸 system prompt ✓。
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest

from qzdap.modules.agent_runtime.adapter.graph.runner import SessionGraphRunner
from qzdap.modules.agent_runtime.application.ports import LLMPort
from qzdap.modules.agent_runtime.domain.catalog import CatalogAgent
from qzdap_llm.client import ChatRequest, LLMChunk, Usage

TENANT = UUID("00000000-0000-0000-0000-000000000001")
WORKSPACE = UUID("00000000-0000-0000-0000-000000000002")
OWNER = UUID("00000000-0000-0000-0000-000000000010")


class _EchoLLM(LLMPort):
    """一句话答完的假模型 ✓。"""

    async def stream(self, req: ChatRequest, **kwargs: object):  # type: ignore[no-untyped-def]
        _ = kwargs
        yield LLMChunk(model=req.model, delta="好的")
        yield LLMChunk(
            model=req.model,
            delta="",
            finish_reason="stop",
            usage=Usage(input_tokens=1, output_tokens=1),
        )

    async def synthetic_chunks(
        self, user_input: str, *, turn_id: UUID | None = None
    ) -> list[dict[str, Any]]:
        _ = (user_input, turn_id)
        return []


class _RecordingMemoryPort:
    def __init__(self, *, raise_exc: Exception | None = None) -> None:
        self._raise = raise_exc
        self.calls: list[dict[str, Any]] = []
        self.writes: list[dict[str, Any]] = []

    async def recall(self, **kwargs: Any) -> list[dict]:
        self.calls.append(dict(kwargs))
        if self._raise is not None:
            raise self._raise
        return [{"id": "m1", "content": "记住我", "score": 0.9}]

    async def write(self, **kwargs: Any) -> dict:
        """记忆写入 —— 轮次收尾会调它 ✓（这里只关心召回 ✓）。"""
        return {"ok": True}

    async def write_turn(self, **kwargs: Any) -> dict:
        """新写入口 ✓（A-26 ✓）—— 轮次收尾用它沉淀记忆 ✓。"""
        self.writes.append(dict(kwargs))
        return {"written": 1, "rejected": 0, "deduplicated": 0}


class _RecordingKnowledgePort:
    def __init__(self, *, raise_exc: Exception | None = None) -> None:
        self._raise = raise_exc
        self.calls: list[dict[str, Any]] = []

    async def search(self, **kwargs: Any) -> list[dict]:
        self.calls.append(dict(kwargs))
        if self._raise is not None:
            raise self._raise
        return [{"id": "k1", "content": "知识片段", "score": 0.8}]


def _agent() -> CatalogAgent:
    return CatalogAgent.create(
        id=uuid4(),
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        name="助手",
        category="企业通用",
        owner="管理员",
        description="",
        model="demo",
    )


async def _run(runner: SessionGraphRunner) -> list[Any]:
    return [
        chunk
        async for chunk in runner.run_graph(
            tenant_id=TENANT,
            workspace_id=WORKSPACE,
            owner_id=OWNER,
            turn_id=uuid4(),
            session_id=uuid4(),
            user_input="你好",
            history=[],
            agent=_agent(),
            model="demo",
        )
    ]


@pytest.mark.asyncio
async def test_memory_recall_is_scoped_to_the_user() -> None:
    """召回**必须带 user_id** —— 漏了就把别人的记忆召回来（X14）✗。"""
    memory = _RecordingMemoryPort()
    runner = SessionGraphRunner(llm=_EchoLLM(), memory_port=memory)  # type: ignore[arg-type]
    await _run(runner)
    assert len(memory.calls) == 1
    call = memory.calls[0]
    assert call["query"] == "你好"
    assert call["tenant_id"] == TENANT
    assert call["workspace_id"] == WORKSPACE
    assert call["user_id"] == OWNER


@pytest.mark.asyncio
async def test_knowledge_search_is_called_with_the_query() -> None:
    knowledge = _RecordingKnowledgePort()
    runner = SessionGraphRunner(llm=_EchoLLM(), knowledge_port=knowledge)  # type: ignore[arg-type]
    await _run(runner)
    assert len(knowledge.calls) == 1
    call = knowledge.calls[0]
    assert call["query"] == "你好"
    assert call["tenant_id"] == TENANT


@pytest.mark.asyncio
async def test_the_agent_knowledge_bindings_reach_the_search_port() -> None:
    """**agent 绑的知识库要传下去** ✓ —— 漏了这条约束就整个失效了 ✗✗。

    ⚠️ 旧路径按 ``agent.knowledge_refs``（只取 enabled ✓）过滤 ✓ ——
    新 Builder 也必须拿到同一组 id ✓（A-26 的接线不能丢这条 ✗）。
    """
    knowledge = _RecordingKnowledgePort()
    runner = SessionGraphRunner(llm=_EchoLLM(), knowledge_port=knowledge)  # type: ignore[arg-type]
    agent = _agent()
    enabled = uuid4()
    disabled = uuid4()
    agent.knowledge_refs = [
        {"id": str(enabled), "enabled": True},
        {"id": str(disabled), "enabled": False},
    ]
    async for _chunk in runner.run_graph(
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        owner_id=OWNER,
        turn_id=uuid4(),
        session_id=uuid4(),
        user_input="你好",
        history=[],
        agent=agent,
        model="demo",
    ):
        pass
    assert len(knowledge.calls) == 1
    assert tuple(knowledge.calls[0]["package_ids"]) == (enabled,)


@pytest.mark.asyncio
async def test_a_recall_failure_does_not_break_the_turn() -> None:
    """召回挂了 → **降级**（裸 system prompt），这一轮照跑 ✓。"""
    memory = _RecordingMemoryPort(raise_exc=RuntimeError("memory offline"))
    knowledge = _RecordingKnowledgePort(raise_exc=RuntimeError("knowledge offline"))
    runner = SessionGraphRunner(
        llm=_EchoLLM(),
        memory_port=memory,
        knowledge_port=knowledge,  # type: ignore[arg-type]
    )
    chunks = await _run(runner)
    assert chunks, "这一轮应该照常产出 chunk ✓"
    assert not any(getattr(chunk, "kind", "") == "error" for chunk in chunks)


__all__ = []
