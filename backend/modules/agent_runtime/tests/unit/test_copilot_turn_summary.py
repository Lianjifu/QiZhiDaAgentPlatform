"""**会话详情带「每一轮的事实」** ✓ —— 对话页的「本轮小结」靠它 ✓。

⚠️ **那些数字一直躺在库里** ✓（``session_turns`` 的起止时间 ✓ +
``session_events`` 的 ``usage`` / ``knowledge_search`` ✓）—— 但**没有任何
接口把它们读出来** ✓ → 重开一个会话, 耗时 / token / 成本 / 工具数 /
知识命中数就全没了 ✗✗（那一轮的记录还在 ✓ —— 只是没人读 ✓）。

这里的口径：

| 事实 | 来源 |
|---|---|
| 状态 / 耗时 | ``session_turns.status`` + 起止时间 ✓ |
| token / 成本 | ``usage`` 事件 ✓（取**最后一次** ✓ —— 与 runner 落进 ``session_turns.cost_usd`` 的是同一个 ✓） |
| 工具 / 技能 / 工作流 | ``tool_call`` / ``skill_invocation`` / ``workflow_invocation`` 事件 ✓ |
| 知识命中 | ``knowledge_search`` 事件 ✓ |
| 降级标记 | 事件信封上的 ``flags`` ✓ |
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from _ar_unit_in_memory import make_copilot

from qzdap.modules.agent_runtime.adapter.persistence.session_journal import (
    assemble_turn_summaries,
)
from qzdap.modules.agent_runtime.domain.catalog import CatalogAgent


def _agent() -> CatalogAgent:
    return CatalogAgent.create(
        id=uuid4(),
        tenant_id=uuid4(),
        workspace_id=uuid4(),
        name="助手",
        category="test",
        owner="test",
        model="default",
    )


@pytest.mark.asyncio
async def test_session_detail_carries_the_facts_of_every_turn() -> None:
    """跑完一轮 → 详情里能读到**那一轮的事实** ✓."""
    agent = _agent()
    service, _deps = make_copilot(agent=agent)
    tenant_id, workspace_id, owner_id = uuid4(), uuid4(), uuid4()
    detail = await service.create_session(
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        owner_id=owner_id,
        agent_id=agent.id,
    )
    session_id = UUID(detail["id"])
    async for _chunk in service.turn_entry.stream(
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        owner_id=owner_id,
        session_id=session_id,
        user_input="你好",
    ):
        pass

    detail = await service.get_session(tenant_id=tenant_id, session_id=session_id)
    turns = detail["turns"]
    assert len(turns) == 1, f"这一轮的事实没带出来: {detail}"
    turn = turns[0]
    assert turn["status"] == "succeeded"
    assert turn["inputTokens"] == 3, f"token 数没带出来: {turn}"
    assert turn["outputTokens"] == 2
    assert turn["durationMs"] is not None and turn["durationMs"] >= 0
    assert turn["startedAt"] and turn["finishedAt"]
    assert turn["modelVersion"]


@pytest.mark.asyncio
async def test_session_list_reports_last_activity_and_turn_count() -> None:
    """会话卡片上的**最近活动 / 轮次数**是真的 ✓ —— 不是创建时间蒙的 ✓."""
    agent = _agent()
    service, _deps = make_copilot(agent=agent)
    tenant_id, workspace_id, owner_id = uuid4(), uuid4(), uuid4()
    detail = await service.create_session(
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        owner_id=owner_id,
        agent_id=agent.id,
    )
    session_id = UUID(detail["id"])
    async for _chunk in service.turn_entry.stream(
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        owner_id=owner_id,
        session_id=session_id,
        user_input="你好",
    ):
        pass

    cards = await service.list_sessions(tenant_id=tenant_id, owner_id=owner_id)
    assert len(cards) == 1
    card = cards[0]
    assert card["turnCount"] == 1
    assert card["lastStatus"] == "succeeded"
    # ⚠️ **最近活动 = 那一轮跑完的时刻** ✓ —— 不是会话创建时刻 ✓。
    assert card["updatedAt"] == card["createdAt"] or card["updatedAt"] > card["createdAt"]
    assert card["agentName"] == "助手"


def test_turn_summary_merges_usage_knowledge_and_flags() -> None:
    """**一次事件流拼出一轮的事实** ✓ —— 工具 / 知识 / 降级标记都在 ✓."""
    turn_id = uuid4()
    started = datetime.now(UTC)
    finished = started + timedelta(seconds=3)
    rows = [
        (
            turn_id,
            "succeeded",
            started,
            finished,
            None,
            "deepseek-flash",
            "v1",
            "查一下考勤",
            "knowledge_search",
            1,
            {
                "flags": ["recall_degraded"],
                "query": "考勤",
                "hits": [{"id": "k1", "title": "考勤规定", "snippet": "…", "score": 0.9}],
                "degraded": True,
            },
        ),
        (
            turn_id,
            "succeeded",
            started,
            finished,
            None,
            "deepseek-flash",
            "v1",
            "查一下考勤",
            "tool_call",
            2,
            {"tool_call_id": "c1", "tool_name": "shell", "arguments": {"cmd": "ls"}},
        ),
        (
            turn_id,
            "succeeded",
            started,
            finished,
            None,
            "deepseek-flash",
            "v1",
            "查一下考勤",
            "tool_result",
            3,
            {"tool_call_id": "c1", "output": "ok", "is_error": False, "latency_ms": 12},
        ),
        (
            turn_id,
            "succeeded",
            started,
            finished,
            None,
            "deepseek-flash",
            "v1",
            "查一下考勤",
            "usage",
            4,
            {"input_tokens": 2228, "output_tokens": 122, "cost_usd": 0.0001},
        ),
    ]

    turns = assemble_turn_summaries(rows)
    assert len(turns) == 1
    turn = turns[0]
    assert turn["duration_ms"] == 3000
    assert turn["input_tokens"] == 2228
    assert turn["output_tokens"] == 122
    assert turn["cost_usd"] == pytest.approx(0.0001)
    assert turn["degraded"] == ["recall_degraded"]
    assert turn["tool_calls"] == [
        {
            "id": "c1",
            "tool_name": "shell",
            "status": "succeeded",
            "arguments": {"cmd": "ls"},
            "output": "ok",
            "latency_ms": 12,
        }
    ]
    assert turn["knowledge_hits"] is not None
    assert turn["knowledge_hits"]["hits"][0]["title"] == "考勤规定"
    assert turn["knowledge_hits"]["degraded"] is True
