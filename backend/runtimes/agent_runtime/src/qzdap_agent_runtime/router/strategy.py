"""Router 的策略实现 —— 规则链（Router 方案 §3.1）。

规则优先级（**从高到低**）：

===  ==================  ============================================
优先级  规则                依据
===  ==================  ============================================
1    **会话粘性**          目标会话已存在 → 沿用其 agent（需要 Session 的
                          只读 ``lookup(session_key)`` 端口，Stage 2 接上）
2    **显式指定**          调用方明确指定的 agent（web 前端的 agent 选择器）
3    **业务线策略**        ``category`` / ``profile.routing.business_lines`` 命中
4    **用户标签策略**      ``visible_scope`` ∩ 用户属性（``UserDirectoryPort``）
5    **兜底默认 agent**    ``profile.routing.default`` 的 agent
===  ==================  ============================================

**规则 1 压过规则 2**：会话已存在时，粘性赢 —— 会话中途换 agent 会让历史
上下文的解释方式突变。但**必须留痕**：``reason="sticky_session_binding"`` +
``overridden_agent_id``，否则用户「换个 agent 重新问」会发现没生效，且事后
无从解释（§3.1 的备注）。

**兜底必须安全**：命中不了任何规则时走默认 agent，**不得因为路由失败而丢
消息**（§3.1）。只有连默认 agent 都没有配置时才抛
:class:`RoutingUnavailable`。
"""

from __future__ import annotations

from time import monotonic
from typing import Protocol
from uuid import UUID

from qzdap_agent_runtime.router.types import (
    RULE_VERSION,
    STRATEGY_ID,
    AgentCandidate,
    AgentCatalogPort,
    RouteDecision,
    RoutingAgent,
    RoutingRequest,
    RoutingUnavailable,
    UserAttributes,
    UserDirectoryPort,
)
from qzdap_observability.metrics import record_router_route

#: 视为「已发布」的状态 —— 与 ``AgentCatalogService.get_published`` 同一口径
#: （"graying" = 灰度中，仍可用）。
PUBLISHED_STATUSES = frozenset({"published", "graying"})

#: ``visible_scope`` 里的**范围类型**关键字 —— 命中它等于「该范围内所有人可见」
#:（默认的 ``["部门"]`` 就是这个意思：凡属某部门者可见）。
GENERIC_SCOPES = frozenset({"部门", "全员", "全部", "department", "dept", "all", "*"})


class Strategy(Protocol):
    """路由策略的端口（§9 的 ``Router ← Agent Catalog`` 那一侧的契约）。"""

    async def decide(self, request: RoutingRequest) -> RouteDecision: ...


class RuleChainStrategy:
    """规则链实现 —— 五条规则按优先级依次尝试。

    **候选池来自 ``admin_agents``**（经 :class:`AgentCatalogPort`）——
    策略是 agent 的属性，不新建策略表（§3.3）。
    """

    def __init__(
        self,
        *,
        catalog: AgentCatalogPort,
        users: UserDirectoryPort | None = None,
        strategy_id: str = STRATEGY_ID,
        rule_version: str = RULE_VERSION,
    ) -> None:
        self._catalog = catalog
        self._users = users
        self._strategy_id = strategy_id
        self._rule_version = rule_version

    async def decide(self, request: RoutingRequest) -> RouteDecision:
        started = monotonic()
        agents = await self._catalog.list_agents(
            tenant_id=request.tenant_id, workspace_id=request.workspace_id
        )
        pool = [a for a in agents if a.status in PUBLISHED_STATUSES]

        decision = self._rule_sticky(request, pool)
        if decision is None:
            decision = self._rule_explicit(request, agents, pool)
        if decision is None:
            decision = self._rule_business_line(request, pool)
        if decision is None:
            decision = await self._rule_user_tag(request, pool)
        if decision is None:
            decision = self._rule_fallback(pool)
        if decision is None:
            # 一条规则都没命中 → **不静默**：记 rejected 并报错（§3.1 的兜底要求）。
            record_router_route(
                strategy="unmatched",
                outcome="rejected",
                duration_s=monotonic() - started,
            )
            raise RoutingUnavailable(
                "no routing rule matched and the workspace has no default agent "
                f"(tenant={request.tenant_id}, workspace={request.workspace_id})"
            )
        record_router_route(
            strategy=decision.source,
            outcome="fallback" if decision.source == "fallback" else "matched",
            duration_s=monotonic() - started,
        )
        return decision

    # ── 规则 1：会话粘性 ────────────────────────────────────────────────

    def _rule_sticky(
        self, request: RoutingRequest, pool: list[RoutingAgent]
    ) -> RouteDecision | None:
        """沿用既有会话的 agent。

        ⚠️ ``sticky_agent`` 由 **Session 的只读 ``lookup(session_key)``** 提供
        —— Router **不自己查会话表**（§2 的两步流程）。
        """
        target = request.sticky_agent
        if target is None:
            return None
        overridden = (
            request.explicit_agent_id
            if request.explicit_agent_id and request.explicit_agent_id != target.agent_id
            else None
        )
        reason = "sticky_session_binding"
        if overridden is not None:
            reason = f"sticky_session_binding(overrode explicit {overridden})"
        winner = next(
            (a for a in pool if a.agent_id == target.agent_id),
            None,
        )
        return self._decision(
            agent_id=target.agent_id,
            agent_version=target.agent_version,
            source="sticky",
            confidence=1.0,
            reason=reason,
            winner=winner,
            pool=pool,
            overridden_agent_id=overridden,
        )

    # ── 规则 2：显式指定 ────────────────────────────────────────────────

    def _rule_explicit(
        self,
        request: RoutingRequest,
        agents: list[RoutingAgent],
        pool: list[RoutingAgent],
    ) -> RouteDecision | None:
        """调用方明确指定的 agent。

        ⚠️ **指定了但目录里没有**（或没发布）时**仍然采用** —— 校验交给下游
        的 ``get_published``（它报「agent 已停用」），路由层不重复实现校验，
        也不把「用户点了没发布的 agent」悄悄换成别的 agent。
        """
        target_id = request.explicit_agent_id
        if target_id is None:
            return None
        winner = next((a for a in agents if a.agent_id == target_id), None)
        known = winner is not None
        return self._decision(
            agent_id=target_id,
            agent_version=winner.agent_version if winner else "",
            source="explicit",
            confidence=0.9 if known else 0.6,
            reason=("explicit_agent_requested" if known else "explicit_agent_not_in_catalog"),
            winner=winner,
            pool=pool,
        )

    # ── 规则 3：业务线 ──────────────────────────────────────────────────

    def _rule_business_line(
        self, request: RoutingRequest, pool: list[RoutingAgent]
    ) -> RouteDecision | None:
        """业务线命中 —— ``category`` 或 ``profile.routing.business_lines``。"""
        line = (request.business_line or "").strip()
        if not line:
            return None
        matched = [
            agent for agent in pool if any(_same_scope(item, line) for item in agent.business_lines)
        ]
        if not matched:
            return None
        winner = _best(matched)
        return self._decision(
            agent_id=winner.agent_id,
            agent_version=winner.agent_version,
            source="business_line",
            confidence=0.7,
            reason=f"business_line:{line}",
            winner=winner,
            pool=pool,
        )

    # ── 规则 4：用户标签 ────────────────────────────────────────────────

    async def _rule_user_tag(
        self, request: RoutingRequest, pool: list[RoutingAgent]
    ) -> RouteDecision | None:
        """``visible_scope`` ∩ 用户属性（或 agent 的标签 ∩ 用户标签）。

        ⚠️ **部门没有结构化字段**（§1.5）—— 这里只能做近似：
        ``visible_scope`` 命中用户的部门/标签/角色之一即算命中；
        ``visible_scope`` 里写的是范围类型（如默认的 ``["部门"]``）时，
        用户只要有部门归属就算命中。
        """
        attributes = await self._user_attributes(request)
        if not attributes.all_values():
            return None
        values = attributes.all_values()
        matched: list[RoutingAgent] = []
        for agent in pool:
            scope_hit = any(_scope_matches(scope, attributes) for scope in agent.visible_scope)
            tag_hit = any(_same_scope(tag, value) for tag in agent.routing_tags for value in values)
            if scope_hit or tag_hit:
                matched.append(agent)
        if not matched:
            return None
        winner = _best(matched)
        return self._decision(
            agent_id=winner.agent_id,
            agent_version=winner.agent_version,
            source="user_tag",
            confidence=0.5,
            reason="user_tag_scope_match",
            winner=winner,
            pool=pool,
        )

    async def _user_attributes(self, request: RoutingRequest) -> UserAttributes:
        """用户属性 = identity 目录 + 请求里的 roles。

        ⚠️ 没有 ``UserDirectoryPort`` 时**只用 roles** —— 拿不到部门就拿不到，
        不猜。
        """
        roles = frozenset(request.roles)
        if self._users is None:
            return UserAttributes(roles=roles)
        attrs = await self._users.get_user_attributes(
            tenant_id=request.tenant_id, user_id=request.user_id
        )
        return UserAttributes(
            departments=attrs.departments,
            tags=attrs.tags,
            roles=attrs.roles | roles,
        )

    # ── 规则 5：兜底 ────────────────────────────────────────────────────

    def _rule_fallback(self, pool: list[RoutingAgent]) -> RouteDecision | None:
        """工作区的兜底默认 agent（``profile.routing.default``）。"""
        defaults = [agent for agent in pool if agent.is_default]
        if not defaults:
            return None
        winner = _best(defaults)
        return self._decision(
            agent_id=winner.agent_id,
            agent_version=winner.agent_version,
            source="fallback",
            confidence=0.1,
            reason="default_agent",
            winner=winner,
            pool=pool,
        )

    # ── 组装 ────────────────────────────────────────────────────────────

    def _decision(
        self,
        *,
        agent_id: UUID,
        agent_version: str,
        source: str,
        confidence: float,
        reason: str,
        winner: RoutingAgent | None,
        pool: list[RoutingAgent],
        overridden_agent_id: UUID | None = None,
    ) -> RouteDecision:
        candidates: list[AgentCandidate] = []
        if winner is not None:
            candidates.append(
                AgentCandidate(
                    agent_id=winner.agent_id,
                    agent_version=winner.agent_version,
                    name=winner.name,
                    reason=reason,
                    score=confidence,
                )
            )
        for agent in pool:
            if winner is not None and agent.agent_id == winner.agent_id:
                continue
            candidates.append(
                AgentCandidate(
                    agent_id=agent.agent_id,
                    agent_version=agent.agent_version,
                    name=agent.name,
                    reason="not_matched",
                    score=0.0,
                )
            )
        return RouteDecision(
            agent_id=agent_id,
            agent_version=agent_version,
            strategy_id=self._strategy_id,
            rule_version=self._rule_version,
            confidence=confidence,
            reason=reason,
            candidates=tuple(candidates),
            source=source,  # type: ignore[arg-type]
            overridden_agent_id=overridden_agent_id,
        )


def _best(agents: list[RoutingAgent]) -> RoutingAgent:
    """同一条规则内的最优候选 —— 优先级高者优先，同优先级按名字定序。

    ⚠️ **必须确定性**：同样的候选池要给出同样的结果，否则路由不可复现、
    评估指标（§3.4）没有意义。
    """
    return min(agents, key=lambda a: (-a.priority, a.name, str(a.agent_id)))


def _same_scope(left: str, right: str) -> bool:
    """两个范围/标签是否指同一个东西 —— 大小写与首尾空白不敏感。"""
    return left.strip().casefold() == right.strip().casefold()


def _scope_matches(scope: str, attributes: UserAttributes) -> bool:
    """``visible_scope`` 的一条是否命中用户。

    - 具体部门/角色名 → 直接相等；
    - 范围类型关键字（"部门"）→ 用户**有部门归属**即命中。
    """
    key = scope.strip().casefold()
    if key in GENERIC_SCOPES:
        return bool(attributes.departments)
    return any(_same_scope(scope, value) for value in attributes.all_values())
