"""**IM 渠道不挂起审批** ✓（2026-10-31）。

⚠️ **为什么** ✓ —— IM 侧**没有人能完成审批** ✓：
- 入站**没有审批回调** ✓（卡片按钮点了回不来 ✓）；
- IM 的 actor 是**渠道登记的服务账号** ✓（= 发起人 ✓）→ 治理域的
  「**审批人不能是发起人**」✓ 会**直接拒掉** ✓（`APPROVER_MUST_DIFFER` ✓）。

→ 挂起一个**永远不会被批准**的审批 ✓ = **这一轮永远卡住** ✗✗
→ **需要审批的工具不暴露给模型** ✓（IM）✓；web 侧照旧 ✓（人在前端点 ✓）。

验收 ✓：
- **IM 渠道的轮次带 `allow_approval=False`** ✓；
- **web / api 的轮次照旧能挂起** ✓（`allow_approval=True` ✓）。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID, uuid4

import pytest
from _ar_unit_in_memory import (
    InMemoryIdempotencyStore,
    InMemorySessionJournal,
    InMemoryTurnRepository,
    make_dependencies,
)

from qzdap.modules.agent_runtime.application.copilot import CopilotSessionService
from qzdap.modules.agent_runtime.domain.catalog import CatalogAgent
from qzdap_agent_runtime.gateway.idempotency import IdempotencyGuard
from qzdap_agent_runtime.gateway.types import ChannelType
from qzdap_kernel.ids import TenantId, UserId, WorkspaceId


class _RecordingTurnRunner:
    """**只记请求** ✓ —— 这一条只关心「轮次带的那个标志」✓。"""

    def __init__(self) -> None:
        self.requests: list[Any] = []

    async def run(self, *, request: Any) -> AsyncIterator[Any]:
        self.requests.append(request)
        return
        yield  # pragma: no cover —— 让它成为异步生成器 ✓


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


async def _make_service(*, agent: CatalogAgent, owner_id: UserId):
    deps = make_dependencies()
    journal = InMemorySessionJournal()
    deps["journal"] = journal
    deps["turns"] = InMemoryTurnRepository(journal)
    runner = _RecordingTurnRunner()
    svc = CopilotSessionService(
        sessions=deps["sessions"],
        turns=deps["turns"],
        messages=_Messages(),
        catalog=_Catalog(agent),
        events=deps["events"],
        graph=deps["llm"],
        idempotency=IdempotencyGuard(InMemoryIdempotencyStore()),
        journal=journal,
        claim=deps["sessions"].claim,
        turn_runner=runner,
    )
    tid = TenantId(agent.tenant_id)
    wid = WorkspaceId(agent.workspace_id)
    detail = await svc.create_session(
        tenant_id=tid, workspace_id=wid, owner_id=owner_id, agent_id=agent.id
    )
    return svc, runner, detail["id"], tid, wid


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "channel",
    [ChannelType.FEISHU, ChannelType.WECHATWORK, ChannelType.DINGTALK],
)
async def test_the_im_channels_cannot_suspend_for_approval(channel: ChannelType) -> None:
    """**IM 渠道的轮次不允许挂起审批** ✓（没有人能批 ✓ → 挂了就是卡死 ✓）。"""
    agent = _agent()
    owner_id = UserId(UUID(int=3))
    svc, runner, sid, tid, wid = await _make_service(agent=agent, owner_id=owner_id)
    async for _chunk in svc.stream_turn(
        tenant_id=tid,
        workspace_id=wid,
        owner_id=owner_id,
        session_id=UUID(sid),
        user_input="嗨",
        channel=channel,
    ):
        pass
    assert runner.requests, "这一轮应该真的跑了"
    assert runner.requests[-1].allow_approval is False


@pytest.mark.asyncio
@pytest.mark.parametrize("channel", [ChannelType.WEB, ChannelType.API])
async def test_the_web_channels_keep_the_approval(channel: ChannelType) -> None:
    """**web / api 照旧能挂起审批** ✓（人在前端点 ✓ —— 不受影响 ✓）。"""
    agent = _agent()
    owner_id = UserId(UUID(int=3))
    svc, runner, sid, tid, wid = await _make_service(agent=agent, owner_id=owner_id)
    async for _chunk in svc.stream_turn(
        tenant_id=tid,
        workspace_id=wid,
        owner_id=owner_id,
        session_id=UUID(sid),
        user_input="嗨",
        channel=channel,
    ):
        pass
    assert runner.requests
    assert runner.requests[-1].allow_approval is True
