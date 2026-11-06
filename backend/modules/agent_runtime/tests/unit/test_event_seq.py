"""**事件序号不撞车** ✓ —— 同一轮里写事件的不止一处 ✓。

⚠️ **踩过的坑** ✓ —— 事件表主键是 ``(turn_id, seq)`` ✓，而写事件的有两处 ✓：
轮次 runner ✓（一路 chunk ✓）+ 专家选择留痕 ✓（``agent.expert.selected`` ✓）。
两边各自从 1 数数 → **撞唯一键** ✓ → 整轮 500 ✓（开发环境没配模型时必现 ✓）。

现在的口径 ✓：**号统一从库里取** ✓（``next_event_seq`` ✓ = max+1 ✓）。
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest

from qzdap.modules.agent_runtime.adapter.graph.runner import SessionGraphRunner
from qzdap.modules.agent_runtime.application.copilot import CopilotSessionService
from qzdap.modules.agent_runtime.domain.catalog import CatalogAgent
from qzdap_agent_runtime.gateway.idempotency import IdempotencyGuard

from ._in_memory import (
    InMemoryCatalog,
    InMemoryIdempotencyStore,
    InMemoryMessages,
    InMemorySessionJournal,
    make_dependencies,
    make_turn_entry,
)


class _CompetingWriterJournal(InMemorySessionJournal):
    """模拟「同一轮里**别人**先写了事件」✓ —— 专家选择留痕 ✓。"""

    async def start_turn(self, **kwargs: Any) -> None:  # type: ignore[no-untyped-def]
        await super().start_turn(**kwargs)
        await self.append_event(
            turn_id=kwargs["turn_id"],
            seq=1,
            event_type="agent.expert.selected",
            payload={"agent": "别的写者"},
        )


@pytest.mark.asyncio
async def test_runner_events_continue_after_another_writer() -> None:
    """runner 的第一条事件**接在别人那条后面** ✓ —— 不撞 (turn_id, seq) ✓."""
    tid, wid, uid = uuid4(), uuid4(), uuid4()
    agent = CatalogAgent.create(
        id=uuid4(),
        tenant_id=tid,
        workspace_id=wid,
        name="t",
        category="test",
        owner="test",
        model="default",
    )
    deps = make_dependencies()
    messages = InMemoryMessages()
    journal = _CompetingWriterJournal()
    runner = SessionGraphRunner(llm=deps["llm"])
    svc = CopilotSessionService(
        sessions=deps["sessions"],
        turns=deps["turns"],
        messages=messages,
        catalog=InMemoryCatalog(agent),
        events=deps["events"],
        graph=runner,
        journal=journal,
        turn_entry=make_turn_entry(
            sessions=deps["sessions"],
            messages=messages,
            catalog=InMemoryCatalog(agent),
            graph=runner,
            journal=journal,
            events=deps["events"],
            idempotency=IdempotencyGuard(InMemoryIdempotencyStore()),
            claim=deps["sessions"].claim,
        ),
    )
    detail = await svc.create_session(
        tenant_id=tid, workspace_id=wid, owner_id=uid, agent_id=agent.id
    )
    chunks = [
        chunk
        async for chunk in svc.turn_entry.stream(
            tenant_id=tid,
            workspace_id=wid,
            owner_id=uid,
            session_id=UUID(detail["id"]),
            user_input="hi",
        )
    ]
    assert chunks

    turn_id = next(iter(journal.events))
    seqs = [event.seq for event in journal.events[turn_id]]
    assert len(seqs) == len(set(seqs)), f"序号撞了: {seqs}"
    assert seqs[0] == 1, "别人的那条先落"
    assert seqs[1] == 2, f"runner 的第一条要接在后面, 实际 {seqs}"
