"""**渠道入站也走 Router 的规则链** ✓（台账 **R19** ✓）。

验收覆盖 ✓：

- **agent 由规则链选出** ✓（不是「直取渠道登记的 agent」✓）；
- **粘性优先** ✓（既有会话的 agent 作为规则 1 的输入 ✓）；
- **路由不可用 → 不丢消息** ✓（退回渠道登记的 agent ✓）；
- **没有策略 = 旧行为** ✓（降级路径 ✓）。
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest

from qzdap.modules.agent_runtime.application.channel_turn import ChannelTurnService
from qzdap_agent_runtime.gateway.types import ChannelType, IdempotencyKey, KeySource
from qzdap_agent_runtime.router.types import (
    AgentCandidate,
    RouteDecision,
    RoutingRequest,
    RoutingUnavailable,
)
from qzdap_agent_runtime.session.manager import AgentBinding, SessionRef


class _FakeSessions:
    """``SessionManagerPort`` 的替身 ✓ —— 记下「用哪个 agent 建的会话」✓。"""

    def __init__(self, existing: SessionRef | None = None) -> None:
        self.existing = existing
        self.binding: AgentBinding | None = None
        self.metadata: dict[str, Any] | None = None
        self.lookups: list[str] = []

    async def lookup(self, *, session_key: str, tenant_id: UUID) -> SessionRef | None:
        self.lookups.append(session_key)
        return self.existing

    async def resolve_or_create(self, *, identity, agent) -> SessionRef:  # type: ignore[no-untyped-def]
        self.binding = agent
        self.metadata = dict(identity.metadata)
        return SessionRef(
            session_id=uuid4(),
            tenant_id=identity.tenant_id,
            workspace_id=identity.workspace_id,
            owner_id=identity.owner_id,
            agent_id=agent.agent_id,
            agent_version=agent.agent_version,
            status="open",  # type: ignore[arg-type]
            created=True,
        )


class _FakeCopilot:
    """门面替身 —— 这一条只关心路由 ✓（不跑轮次 ✓）。"""

    def __init__(self) -> None:
        self.session_ids: list[UUID] = []

    def bind_ports(self, **ports: Any) -> None:
        return


class _FakeTurnEntry:
    """**跑一轮**的入口替身 ✓（S-21b ✓ —— 渠道侧走模块侧入口 ✓）。"""

    def __init__(self) -> None:
        self.session_ids: list[UUID] = []

    async def stream(self, **kwargs: Any):  # type: ignore[no-untyped-def]
        self.session_ids.append(kwargs["session_id"])
        from qzdap_schema.dtos.turn import DoneChunk

        yield DoneChunk(turn_id=uuid4(), seq=1, final_message="好的")


class _FakeStrategy:
    """**可控的策略** ✓ —— 记下它收到的请求 ✓。"""

    def __init__(self, decision: RouteDecision | None = None, *, unavailable: bool = False) -> None:
        self.decision = decision
        self.unavailable = unavailable
        self.requests: list[RoutingRequest] = []

    async def decide(self, request: RoutingRequest) -> RouteDecision:
        self.requests.append(request)
        if self.unavailable:
            raise RoutingUnavailable("no rule matched")
        assert self.decision is not None
        return self.decision


def _decision(agent_id: UUID, *, source: str = "user_tag") -> RouteDecision:
    return RouteDecision(
        agent_id=agent_id,
        agent_version="v9",
        strategy_id="rule-chain",
        rule_version="v1",
        confidence=0.5,
        reason="user_tag_scope_match",
        candidates=(
            AgentCandidate(
                agent_id=agent_id,
                agent_version="v9",
                name="路由出来的 agent",
                reason="user_tag_scope_match",
                score=0.5,
            ),
        ),
        source=source,  # type: ignore[arg-type]
    )


def _request(*, agent_id: UUID, roles: tuple[str, ...] = ()) -> Any:
    from qzdap_agent_runtime.session.channel_turn import ChannelTurnRequest

    return ChannelTurnRequest(
        tenant_id=uuid4(),
        workspace_id=uuid4(),
        owner_id=uuid4(),
        agent_id=agent_id,
        agent_version="v1",
        channel_session_key="channel-1:chat-1",
        channel_type=ChannelType.FEISHU,
        user_input="你好",
        idempotency=IdempotencyKey(
            value=f"platform|{uuid4()}",
            source=KeySource.PLATFORM_MESSAGE_ID,
            strength="strong",
            expires_at=None,  # type: ignore[arg-type]
        ),
        metadata={"channel_type": "feishu", "roles": list(roles)},
    )


@pytest.mark.asyncio
async def test_the_agent_comes_from_the_rule_chain() -> None:
    """**agent 由规则链选出** ✓（不是直取渠道登记的 agent ✓）。"""
    channel_agent = uuid4()
    routed_agent = uuid4()
    strategy = _FakeStrategy(_decision(routed_agent))
    sessions = _FakeSessions()
    service = ChannelTurnService(
        sessions=sessions,  # type: ignore[arg-type]
        copilot=_FakeCopilot(),  # type: ignore[arg-type]
        turn_entry=_FakeTurnEntry(),  # type: ignore[arg-type]
        strategy=strategy,  # type: ignore[arg-type]
    )
    await service.run(_request(agent_id=channel_agent))
    assert sessions.binding is not None
    assert sessions.binding.agent_id == routed_agent
    assert sessions.binding.agent_version == "v9"
    # ⚠️ **渠道登记的 agent 只是「显式指定」这一条规则的输入** ✓。
    assert strategy.requests[0].explicit_agent_id == channel_agent


@pytest.mark.asyncio
async def test_the_existing_session_feeds_the_sticky_rule() -> None:
    """**粘性**：既有会话的 agent 作为规则 1 的输入 ✓。"""
    channel_agent = uuid4()
    sticky_agent = uuid4()
    existing = SessionRef(
        session_id=uuid4(),
        tenant_id=uuid4(),
        workspace_id=uuid4(),
        owner_id=uuid4(),
        agent_id=sticky_agent,
        agent_version="v3",
        status="open",  # type: ignore[arg-type]
    )
    strategy = _FakeStrategy(_decision(sticky_agent, source="sticky"))
    sessions = _FakeSessions(existing=existing)
    service = ChannelTurnService(
        sessions=sessions,  # type: ignore[arg-type]
        copilot=_FakeCopilot(),  # type: ignore[arg-type]
        turn_entry=_FakeTurnEntry(),  # type: ignore[arg-type]
        strategy=strategy,  # type: ignore[arg-type]
    )
    await service.run(_request(agent_id=channel_agent))
    assert strategy.requests[0].sticky_agent is not None
    assert strategy.requests[0].sticky_agent.agent_id == sticky_agent
    assert strategy.requests[0].sticky_agent.agent_version == "v3"
    assert sessions.binding is not None
    assert sessions.binding.agent_id == sticky_agent


@pytest.mark.asyncio
async def test_the_roles_reach_the_rule_chain() -> None:
    """**服务账号的角色** ✓ —— 进「用户标签」规则 ✓。"""
    strategy = _FakeStrategy(_decision(uuid4()))
    sessions = _FakeSessions()
    service = ChannelTurnService(
        sessions=sessions,  # type: ignore[arg-type]
        copilot=_FakeCopilot(),  # type: ignore[arg-type]
        turn_entry=_FakeTurnEntry(),  # type: ignore[arg-type]
        strategy=strategy,  # type: ignore[arg-type]
    )
    await service.run(_request(agent_id=uuid4(), roles=("客服",)))
    assert strategy.requests[0].roles == frozenset({"客服"})


@pytest.mark.asyncio
async def test_an_unmatched_routing_does_not_drop_the_message() -> None:
    """**路由不可用 → 不丢消息** ✓（退回渠道登记的 agent ✓）。"""
    channel_agent = uuid4()
    strategy = _FakeStrategy(unavailable=True)
    sessions = _FakeSessions()
    service = ChannelTurnService(
        sessions=sessions,  # type: ignore[arg-type]
        copilot=_FakeCopilot(),  # type: ignore[arg-type]
        turn_entry=_FakeTurnEntry(),  # type: ignore[arg-type]
        strategy=strategy,  # type: ignore[arg-type]
    )
    result = await service.run(_request(agent_id=channel_agent))
    assert result.final_message == "好的"
    assert sessions.binding is not None
    assert sessions.binding.agent_id == channel_agent


@pytest.mark.asyncio
async def test_without_a_strategy_the_old_behavior_stays() -> None:
    """**没有策略 = 旧行为** ✓（降级路径 ✓）。"""
    channel_agent = uuid4()
    sessions = _FakeSessions()
    service = ChannelTurnService(
        sessions=sessions,  # type: ignore[arg-type]
        copilot=_FakeCopilot(),  # type: ignore[arg-type]
        turn_entry=_FakeTurnEntry(),  # type: ignore[arg-type]
    )
    await service.run(_request(agent_id=channel_agent))
    assert sessions.binding is not None
    assert sessions.binding.agent_id == channel_agent
    assert sessions.binding.agent_version == "v1"


@pytest.mark.asyncio
async def test_the_route_decision_is_left_on_the_session() -> None:
    """**路由决策随会话留痕** ✓（轮次行能回答「为什么是这个 agent」✓）。"""
    strategy = _FakeStrategy(_decision(uuid4()))
    sessions = _FakeSessions()
    service = ChannelTurnService(
        sessions=sessions,  # type: ignore[arg-type]
        copilot=_FakeCopilot(),  # type: ignore[arg-type]
        turn_entry=_FakeTurnEntry(),  # type: ignore[arg-type]
        strategy=strategy,  # type: ignore[arg-type]
    )
    await service.run(_request(agent_id=uuid4()))
    assert sessions.metadata is not None
    decision = sessions.metadata["route_decision"]
    assert decision["source"] == "user_tag"
    assert decision["reason"] == "user_tag_scope_match"
