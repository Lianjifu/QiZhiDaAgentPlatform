"""**整轮超时** ✓ —— 上游挂住时轮次不能永远占着连接 ✗✗。

⚠️ **超时卡在「等下一片」上** ✓ —— 消费者自己的处理时间不算进去 ✓
（慢客户端不该被误杀 ✗✗）。
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID, uuid4

import pytest

from qzdap.modules.agent_runtime.adapter.graph.runner import SessionGraphRunner
from qzdap.modules.agent_runtime.application.copilot import CopilotSessionService
from qzdap.modules.agent_runtime.domain.catalog import CatalogAgent
from qzdap_agent_runtime.gateway.idempotency import IdempotencyGuard
from qzdap_kernel.error_codes import ErrorCode

from ._in_memory import (
    InMemoryCatalog,
    InMemoryIdempotencyStore,
    InMemoryMessages,
    make_dependencies,
    make_turn_entry,
)


class _HangingExecutor:
    """**一个 chunk 都不吐的执行器** ✓（上游挂住 ✓）。"""

    async def run(self, *, request: Any) -> AsyncIterator[Any]:
        await asyncio.sleep(3600)
        yield  # pragma: no cover

    def latest_state(self) -> dict[str, Any]:
        return {}


@pytest.mark.asyncio
async def test_a_hanging_turn_is_cut_off() -> None:
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
    journal = deps["journal"]
    runner = SessionGraphRunner(llm=deps["llm"])
    svc = CopilotSessionService(
        sessions=deps["sessions"],
        turns=deps["turns"],
        messages=messages,
        catalog=InMemoryCatalog(agent),
        events=deps["events"],
        graph=runner,
        journal=journal,
        # ⚠️ **执行器换成挂住的那个** ✓ —— 上游不吐东西 ✓。
        turn_entry=make_turn_entry(
            sessions=deps["sessions"],
            messages=messages,
            catalog=InMemoryCatalog(agent),
            graph=runner,
            journal=journal,
            events=deps["events"],
            idempotency=IdempotencyGuard(InMemoryIdempotencyStore()),
            claim=deps["sessions"].claim,
            executor=_HangingExecutor(),
            timeout_seconds=0.05,
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
    errors = [chunk for chunk in chunks if chunk.kind == "error"]
    assert errors, "挂住的轮次必须被掐断"
    assert errors[0].code == ErrorCode.AGENT_TURN_TIMEOUT.value
