"""Router 规则链的单测（Router 方案 §3.1 的决策链 + §3.2 的 ``RouteDecision``）。

⚠️ 这里测的是**契约层**的规则链 —— 不碰数据库、不碰 FastAPI。
候选池与用户属性都是替身，规则本身必须是纯逻辑。
"""

from __future__ import annotations

from uuid import UUID

import pytest

from qzdap_agent_runtime.router.strategy import RuleChainStrategy
from qzdap_agent_runtime.router.types import (
    AgentTarget,
    RouteDecision,
    RoutingAgent,
    RoutingRequest,
    RoutingUnavailable,
    UserAttributes,
)

TENANT = UUID("00000000-0000-0000-0000-000000000001")
WORKSPACE = UUID("00000000-0000-0000-0000-000000000002")
USER = UUID("00000000-0000-0000-0000-000000000010")

AGENT_A = UUID("00000000-0000-0000-0000-0000000000a1")
AGENT_B = UUID("00000000-0000-0000-0000-0000000000b1")
AGENT_C = UUID("00000000-0000-0000-0000-0000000000c1")


class _Catalog:
    def __init__(self, agents: list[RoutingAgent]) -> None:
        self._agents = agents

    async def list_agents(self, *, tenant_id, workspace_id):  # type: ignore[no-untyped-def]
        return tuple(self._agents)


class _Users:
    def __init__(self, attributes: UserAttributes) -> None:
        self._attributes = attributes

    async def get_user_attributes(self, *, tenant_id, user_id):  # type: ignore[no-untyped-def]
        return self._attributes


def _agent(
    agent_id: UUID,
    *,
    name: str = "a",
    category: str = "",
    visible_scope: tuple[str, ...] = (),
    tags: tuple[str, ...] = (),
    profile: dict | None = None,
    status: str = "published",
) -> RoutingAgent:
    return RoutingAgent(
        agent_id=agent_id,
        agent_version="v1",
        name=name,
        category=category,
        visible_scope=visible_scope,
        tags=tags,
        profile=profile or {},
        status=status,
    )


def _request(**kwargs) -> RoutingRequest:
    base = {
        "tenant_id": TENANT,
        "workspace_id": WORKSPACE,
        "user_id": USER,
    }
    base.update(kwargs)
    return RoutingRequest(**base)


def _strategy(
    agents: list[RoutingAgent],
    *,
    users: UserAttributes | None = None,
) -> RuleChainStrategy:
    return RuleChainStrategy(
        catalog=_Catalog(agents),
        users=_Users(users) if users is not None else None,
    )


# ── 规则 2：显式指定 ───────────────────────────────────────────────────────


async def test_explicit_agent_wins_over_the_other_rules() -> None:
    strategy = _strategy(
        [
            _agent(AGENT_A, name="默认", profile={"routing": {"default": True}}),
            _agent(AGENT_B, name="别的"),
        ]
    )

    decision = await strategy.decide(_request(explicit_agent_id=AGENT_B))

    assert decision.source == "explicit"
    assert decision.agent_id == AGENT_B
    assert decision.confidence == pytest.approx(0.9)


async def test_explicit_agent_outside_the_catalog_is_still_used() -> None:
    """指定了但目录里没有 → 仍然采用，校验交给下游（不偷偷换成别的 agent）。"""
    strategy = _strategy([_agent(AGENT_A)])

    decision = await strategy.decide(_request(explicit_agent_id=AGENT_B))

    assert decision.source == "explicit"
    assert decision.agent_id == AGENT_B
    assert decision.reason == "explicit_agent_not_in_catalog"


# ── 规则 1：会话粘性 ───────────────────────────────────────────────────────


async def test_sticky_binding_overrides_the_explicit_agent() -> None:
    """粘性压过显式 —— 但**必须留痕**，否则用户「换个 agent 重新问」没交代。"""
    strategy = _strategy([_agent(AGENT_A), _agent(AGENT_B)])

    decision = await strategy.decide(
        _request(
            explicit_agent_id=AGENT_B,
            sticky_agent=AgentTarget(agent_id=AGENT_A, agent_version="v1", name="a"),
        )
    )

    assert decision.source == "sticky"
    assert decision.agent_id == AGENT_A
    assert decision.overridden_agent_id == AGENT_B
    assert "sticky_session_binding" in decision.reason


async def test_sticky_binding_without_an_explicit_agent_records_no_override() -> None:
    strategy = _strategy([_agent(AGENT_A)])

    decision = await strategy.decide(
        _request(sticky_agent=AgentTarget(agent_id=AGENT_A, agent_version="v1", name="a"))
    )

    assert decision.source == "sticky"
    assert decision.overridden_agent_id is None


# ── 规则 3：业务线 ────────────────────────────────────────────────────────


async def test_business_line_matches_the_category() -> None:
    strategy = _strategy(
        [
            _agent(AGENT_A, name="客服", category="客服"),
            _agent(AGENT_B, name="销售", category="销售"),
        ]
    )

    decision = await strategy.decide(_request(business_line="客服"))

    assert decision.source == "business_line"
    assert decision.agent_id == AGENT_A
    assert decision.reason == "business_line:客服"


async def test_business_line_can_come_from_the_routing_profile() -> None:
    strategy = _strategy(
        [
            _agent(
                AGENT_A,
                name="带业务线",
                category="企业通用",
                profile={"routing": {"business_lines": ["法务"]}},
            )
        ]
    )

    decision = await strategy.decide(_request(business_line="法务"))

    assert decision.source == "business_line"
    assert decision.agent_id == AGENT_A


# ── 规则 4：用户标签 ──────────────────────────────────────────────────────


async def test_user_tag_matches_the_visible_scope() -> None:
    strategy = _strategy(
        [
            _agent(AGENT_A, name="财务部", visible_scope=("财务部",)),
            _agent(AGENT_B, name="别的", visible_scope=("法务部",)),
        ],
        users=UserAttributes(departments=("财务部",)),
    )

    decision = await strategy.decide(_request())

    assert decision.source == "user_tag"
    assert decision.agent_id == AGENT_A


async def test_generic_scope_matches_any_department() -> None:
    """``visible_scope=["部门"]``（默认写法）= 凡属某部门者可见。"""
    strategy = _strategy(
        [_agent(AGENT_A, name="通用", visible_scope=("部门",))],
        users=UserAttributes(departments=("销售部",)),
    )

    decision = await strategy.decide(_request())

    assert decision.source == "user_tag"
    assert decision.agent_id == AGENT_A


async def test_user_without_attributes_falls_through() -> None:
    """没有部门/标签/角色 → 用户标签规则不命中（**不猜**）。"""
    strategy = _strategy(
        [_agent(AGENT_A, name="通用", visible_scope=("部门",))],
        users=UserAttributes(),
    )

    with pytest.raises(RoutingUnavailable):
        await strategy.decide(_request())


# ── 规则 5：兜底 ──────────────────────────────────────────────────────────


async def test_fallback_uses_the_configured_default_agent() -> None:
    strategy = _strategy(
        [
            _agent(AGENT_A, name="普通"),
            _agent(AGENT_B, name="默认", profile={"routing": {"default": True}}),
        ]
    )

    decision = await strategy.decide(_request())

    assert decision.source == "fallback"
    assert decision.agent_id == AGENT_B
    assert decision.confidence == pytest.approx(0.1)


async def test_draft_agents_never_win() -> None:
    """未发布的 agent 不进候选池 —— 草稿不能被路由到。"""
    strategy = _strategy(
        [_agent(AGENT_A, name="草稿", status="draft")],
    )

    with pytest.raises(RoutingUnavailable):
        await strategy.decide(_request())


async def test_no_rule_matched_raises_routing_unavailable() -> None:
    strategy = _strategy([_agent(AGENT_A)])

    with pytest.raises(RoutingUnavailable):
        await strategy.decide(_request())


async def test_the_default_agent_is_picked_by_priority() -> None:
    """多个默认 agent → 优先级高的赢，且**结果确定**。"""
    strategy = _strategy(
        [
            _agent(
                AGENT_A,
                name="低",
                profile={"routing": {"default": True, "priority": 1}},
            ),
            _agent(
                AGENT_B,
                name="高",
                profile={"routing": {"default": True, "priority": 9}},
            ),
        ]
    )

    decision = await strategy.decide(_request())

    assert decision.agent_id == AGENT_B


# ── 留痕 ─────────────────────────────────────────────────────────────────


async def test_the_decision_records_the_losers_with_their_scores() -> None:
    """``candidates`` 必须带上落选候选 —— 否则策略调优只能靠猜（§3.2）。"""
    strategy = _strategy(
        [
            _agent(AGENT_A, name="a"),
            _agent(AGENT_B, name="b"),
        ]
    )

    decision = await strategy.decide(_request(explicit_agent_id=AGENT_A))

    names = {c.name: c for c in decision.candidates}
    assert set(names) == {"a", "b"}
    assert names["a"].score == pytest.approx(decision.confidence)
    assert names["b"].score == pytest.approx(0.0)


async def test_the_decision_round_trips_through_jsonb() -> None:
    """决策要能落 ``session_turns.route_decision``（JSONB）→ 必须可序列化。"""
    strategy = _strategy([_agent(AGENT_A), _agent(AGENT_B)])

    decision = await strategy.decide(_request(explicit_agent_id=AGENT_A))
    restored = RouteDecision.from_dict(decision.to_dict())

    assert restored.agent_id == decision.agent_id
    assert restored.source == decision.source
    assert restored.confidence == pytest.approx(decision.confidence)
    assert restored.candidates == decision.candidates


async def test_the_strategy_records_which_rule_matched() -> None:
    """兜底命中率要可查 —— 指标由策略自己打（§12.2）。"""
    from qzdap_observability.metrics import ROUTER_ROUTE_TOTAL

    strategy = _strategy([_agent(AGENT_A, profile={"routing": {"default": True}})])
    before = ROUTER_ROUTE_TOTAL.labels(strategy="fallback", outcome="fallback")._value.get()

    await strategy.decide(_request())

    after = ROUTER_ROUTE_TOTAL.labels(strategy="fallback", outcome="fallback")._value.get()
    assert after == before + 1


async def test_a_rejected_route_is_also_counted() -> None:
    """一条都没命中 → 记 rejected（**不静默**）。"""
    from qzdap_observability.metrics import ROUTER_ROUTE_TOTAL

    strategy = _strategy([_agent(AGENT_A)])
    before = ROUTER_ROUTE_TOTAL.labels(strategy="unmatched", outcome="rejected")._value.get()

    with pytest.raises(RoutingUnavailable):
        await strategy.decide(_request())

    after = ROUTER_ROUTE_TOTAL.labels(strategy="unmatched", outcome="rejected")._value.get()
    assert after == before + 1
