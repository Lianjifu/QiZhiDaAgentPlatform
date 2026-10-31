"""会话用例测试（**copilot 链路** —— 唯一 turn 实现那条 ✓）。

⚠️ 旧的 ``AgentRuntimeService`` 门面与它下面的 ``run_turn`` 用例**已删**
（2026-10-30，Session Stage 5b —— 第二套 turn 实现，台账 X2）✓。
这里保留的是**会话生命周期**的覆盖：建会话 / 关会话 / 跨租户读不到 ✓。
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from _ar_unit_in_memory import make_copilot

from qzdap.modules.agent_runtime.domain import SessionStatus
from qzdap.modules.agent_runtime.domain.catalog import CatalogAgent
from qzdap.modules.agent_runtime.domain.errors import SessionNotFound
from qzdap_schema.ids import (
    AgentId,
    TenantId,
    UserId,
    WorkspaceId,
)


def _make_owners() -> tuple[TenantId, WorkspaceId, UserId, AgentId]:
    return (
        TenantId(uuid4()),
        WorkspaceId(uuid4()),
        UserId(uuid4()),
        AgentId(uuid4()),
    )


def _agent(tid: TenantId, wid: WorkspaceId, aid: AgentId) -> CatalogAgent:
    return CatalogAgent.create(
        id=aid,
        tenant_id=tid,
        workspace_id=wid,
        name="助手",
        category="test",
        owner="test",
        model="default",
    )


@pytest.mark.asyncio
async def test_create_session_persists_and_emits_event() -> None:
    tid, wid, uid, aid = _make_owners()
    agent = _agent(tid, wid, aid)
    svc, deps = make_copilot(agent=agent)

    detail = await svc.create_session(tenant_id=tid, workspace_id=wid, owner_id=uid, agent_id=aid)
    sid = UUID(detail["id"])
    fetched = await deps["sessions"].get(sid)
    assert fetched is not None
    assert fetched.status is SessionStatus.OPEN
    # 版本**绑自目录里的 agent** ✓（会话与版本一起绑，避免中途换版本 ✗）。
    assert fetched.agent_version == agent.version

    event_types = [type(e).__name__ for e in deps["events"].events]
    assert "SessionOpened" in event_types


@pytest.mark.asyncio
async def test_close_session_marks_closed_and_emits_event() -> None:
    tid, wid, uid, aid = _make_owners()
    svc, deps = make_copilot(agent=_agent(tid, wid, aid))
    detail = await svc.create_session(tenant_id=tid, workspace_id=wid, owner_id=uid, agent_id=aid)
    sid = UUID(detail["id"])

    await svc.close_session(tenant_id=tid, session_id=sid)
    closed = await deps["sessions"].get(sid)
    assert closed is not None and closed.status is SessionStatus.CLOSED

    event_types = [type(e).__name__ for e in deps["events"].events]
    assert "SessionClosed" in event_types


@pytest.mark.asyncio
async def test_close_session_is_idempotent() -> None:
    """重复关会话**不报错**、**不多发事件** ✓（客户端重试不该 500）。"""
    tid, wid, uid, aid = _make_owners()
    svc, deps = make_copilot(agent=_agent(tid, wid, aid))
    detail = await svc.create_session(tenant_id=tid, workspace_id=wid, owner_id=uid, agent_id=aid)
    sid = UUID(detail["id"])

    await svc.close_session(tenant_id=tid, session_id=sid)
    await svc.close_session(tenant_id=tid, session_id=sid)
    closed_events = [e for e in deps["events"].events if type(e).__name__ == "SessionClosed"]
    assert len(closed_events) == 1


@pytest.mark.asyncio
async def test_get_session_returns_not_found_for_other_tenant() -> None:
    tid, wid, uid, aid = _make_owners()
    svc, _ = make_copilot(agent=_agent(tid, wid, aid))
    detail = await svc.create_session(tenant_id=tid, workspace_id=wid, owner_id=uid, agent_id=aid)
    other_tenant = TenantId(uuid4())
    with pytest.raises(SessionNotFound):
        await svc.get_session(tenant_id=other_tenant, session_id=UUID(detail["id"]))


__all__ = []
