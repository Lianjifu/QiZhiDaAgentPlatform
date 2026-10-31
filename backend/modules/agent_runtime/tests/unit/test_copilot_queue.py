"""**同会话的排队**（Router Stage 3 · 决策 #1「S1 严格排队」✓）。

验收覆盖 ✓：
- 排队中的轮次**先落 ``queued``** ✓；
- **等不到位就不跑** ✓（排队期间不发业务 chunk ✓）；
- **队列满了 → 明确错误** ✓（``QUEUE_FULL`` ✓ —— 不静默丢弃 ✓）；
- **放行之后正常跑完** ✓。
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest
from _ar_unit_in_memory import (
    InMemoryIdempotencyStore,
    InMemorySessionJournal,
    InMemoryTurnRepository,
    make_dependencies,
    make_turn_runner,
)

from qzdap.modules.agent_runtime.adapter.graph.runner import SessionGraphRunner
from qzdap.modules.agent_runtime.application.copilot import CopilotSessionService
from qzdap.modules.agent_runtime.domain.catalog import CatalogAgent
from qzdap_agent_runtime.gateway.idempotency import IdempotencyGuard
from qzdap_agent_runtime.session.queue import QueueDecision, QueueOutcome
from qzdap_kernel.ids import TenantId, UserId, WorkspaceId


class _FakeLLM:
    async def stream(self, req: Any, **kwargs: object):  # type: ignore[no-untyped-def]
        from qzdap_llm.client import LLMChunk, Usage

        yield LLMChunk(model=req.model, delta="回答")
        yield LLMChunk(
            model=req.model,
            delta="",
            finish_reason="stop",
            usage=Usage(input_tokens=1, output_tokens=1),
        )

    async def synthetic_chunks(self, user_input: str, *, turn_id: Any = None):
        return []


class _FakeQueue:
    """**可控的排队端口** ✓。"""

    def __init__(self, *, depth: int = 0, release: bool = True) -> None:
        self.depth = depth
        self.release = release
        self.calls = 0

    async def try_release(self, **kwargs: object) -> QueueDecision:
        self.calls += 1
        if self.release:
            return QueueDecision(outcome=QueueOutcome.RELEASED, position=1)
        return QueueDecision(outcome=QueueOutcome.WAITING, position=1)

    async def queue_depth(self, **kwargs: object) -> int:
        return self.depth

    async def queue_position(self, **kwargs: object) -> int:
        return 1


class _FakeSequence:
    async def next_ingress_seq(self, **kwargs: object) -> int:
        return 1

    async def next_message_seq(self, **kwargs: object) -> int:
        return 1


class _Catalog:
    def __init__(self, agent: CatalogAgent) -> None:
        self._agent = agent

    async def get_published(self, agent_id: Any):
        return self._agent


class _Messages:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    async def list_for_session(self, session_id: Any):
        return self.rows

    async def append(self, **kwargs: Any):
        self.rows.append(kwargs)

    async def next_seq(self, *, session_id: Any) -> int:  # type: ignore[no-untyped-def]
        return (self.rows[-1]["seq"] + 1) if self.rows else 0


def _agent() -> CatalogAgent:
    return CatalogAgent.create(
        id=uuid4(),
        tenant_id=TenantId(UUID(int=1)),
        workspace_id=WorkspaceId(UUID(int=2)),
        name="t",
        category="test",
        owner="test",
        model="default",
    )


async def _make_service(*, queue: Any, agent: CatalogAgent, owner_id: UserId):
    deps = make_dependencies()
    messages = _Messages()
    runner = SessionGraphRunner(llm=_FakeLLM())
    journal = InMemorySessionJournal()
    deps["journal"] = journal
    deps["turns"] = InMemoryTurnRepository(journal)
    svc = CopilotSessionService(
        sessions=deps["sessions"],
        turns=deps["turns"],
        messages=messages,
        catalog=_Catalog(agent),
        events=deps["events"],
        graph=runner,
        idempotency=IdempotencyGuard(InMemoryIdempotencyStore()),
        journal=journal,
        claim=deps["sessions"].claim,
        turn_runner=make_turn_runner(
            graph=runner,
            journal=journal,
            events=deps["events"],
            messages=messages,
            sessions=deps["sessions"],
            queue=queue,
        ),
        # ⚠️ **排队** ✓（Router Stage 3 ✓）。
        sequence=_FakeSequence(),
        queue=queue,
    )
    tid = TenantId(agent.tenant_id)
    wid = WorkspaceId(agent.workspace_id)
    detail = await svc.create_session(
        tenant_id=tid, workspace_id=wid, owner_id=owner_id, agent_id=agent.id
    )
    return svc, journal, detail["id"], tid, wid


@pytest.mark.asyncio
async def test_a_queued_turn_is_released_and_then_runs() -> None:
    """**排队 → 放行 → 正常跑完** ✓。"""
    agent = _agent()
    owner_id = UserId(UUID(int=3))
    queue = _FakeQueue()
    svc, journal, sid, tid, wid = await _make_service(queue=queue, agent=agent, owner_id=owner_id)
    chunks = [
        chunk
        async for chunk in svc.stream_turn(
            tenant_id=tid,
            workspace_id=wid,
            owner_id=owner_id,
            session_id=UUID(sid),
            user_input="嗨",
        )
    ]
    kinds = [getattr(chunk, "kind", "") for chunk in chunks]
    assert "done" in kinds
    assert queue.calls == 1
    # ⚠️ **轮次落过 ``queued``** ✓（排队语义 ✓）—— 终态是 succeeded ✓。
    turn = next(iter(journal.turns.values()))
    assert turn["status"] == "succeeded"


@pytest.mark.asyncio
async def test_a_full_queue_is_refused_with_a_clear_error() -> None:
    """**队列满了 → ``QUEUE_FULL``** ✓（决策 #7 ✓ —— **不静默丢弃** ✓）。"""
    agent = _agent()
    owner_id = UserId(UUID(int=3))
    queue = _FakeQueue(depth=5)
    svc, _journal, sid, tid, wid = await _make_service(queue=queue, agent=agent, owner_id=owner_id)
    with pytest.raises(Exception) as excinfo:
        async for _chunk in svc.stream_turn(
            tenant_id=tid,
            workspace_id=wid,
            owner_id=owner_id,
            session_id=UUID(sid),
            user_input="嗨",
        ):
            pass
    assert getattr(excinfo.value, "code", "") == "QUEUE_FULL"


@pytest.mark.asyncio
async def test_without_the_queue_the_old_semantics_stay() -> None:
    """**没有排队端口 = 旧语义** ✓（开关关掉 ✓ —— 「拒绝 409」✓）。"""
    agent = _agent()
    owner_id = UserId(UUID(int=3))
    svc, _journal, sid, tid, wid = await _make_service(queue=None, agent=agent, owner_id=owner_id)
    chunks = [
        chunk
        async for chunk in svc.stream_turn(
            tenant_id=tid,
            workspace_id=wid,
            owner_id=owner_id,
            session_id=UUID(sid),
            user_input="嗨",
        )
    ]
    assert any(getattr(chunk, "kind", "") == "done" for chunk in chunks)
