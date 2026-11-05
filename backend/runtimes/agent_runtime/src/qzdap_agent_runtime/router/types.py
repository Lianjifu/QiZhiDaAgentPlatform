"""Router 层的契约 —— Strategy 的输入/输出形状。

依据：``docs/modules/agent-runtime.md``（``RouteDecision`` 与策略链的落点）。

**这一层是契约层** —— 不引框架、不引模块、不装上下文、不调 LLM
（架构测试 ``backend/tests/architecture/test_router_boundary.py`` 守着这条线）。

⚠️ **策略配置的落点不是新表**（§3.3 + §6.4 决策 #3）：策略是 **agent 的属性**，
写在 ``admin_agents`` 已有字段上 ——

======================  ==========================================
策略维度                落点
======================  ==========================================
业务线                  ``admin_agents.category``
用户可见范围            ``admin_agents.visible_scope``
标签                    ``admin_agents.tags``
兜底默认 / 规则偏好      ``admin_agents.profile["routing"]``
======================  ==========================================

``profile["routing"]`` 的 schema（**文档化，不强制**）::

    {
      "default": true,                 # 兜底默认 agent（规则 5）
      "priority": 10,                  # 同规则内的排序优先级，越大越优先
      "business_lines": ["客服"],       # 该 agent 服务的业务线（category 的补充）
      "tags": ["财务"]                 # 该 agent 命中的用户标签
    }
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, runtime_checkable
from uuid import UUID

#: 决策来源 —— 与 §3.1 的五条规则一一对应。
RouteSource = Literal["sticky", "explicit", "business_line", "user_tag", "fallback"]

#: 策略标识 —— 「哪一套规则」在跑。
STRATEGY_ID = "rule-chain"

#: 规则版本 —— 规则改了要改它，否则历史决策无法回放/对比（§3.2）。
RULE_VERSION = "v1"


class RoutingUnavailable(RuntimeError):
    """一条规则都没命中，且工作区没有兜底默认 agent。

    ⚠️ **只在「连兜底都没有」时抛** —— 兜底本身必须安全：命中不了任何规则时
    走默认 agent，**不得因为路由失败而丢消息**（§3.1）。
    """


@dataclass(frozen=True, slots=True)
class AgentCandidate:
    """一个候选 agent 及其命中依据与得分（§3.2 的 ``candidates``）。

    **为什么必须留候选**：路由决策要**可评估** —— 上线后要能回答
    「这条消息为什么走了这个 agent」「改了规则后命中分布变了没有」。
    没有候选与得分，策略调优只能靠猜。
    """

    agent_id: UUID
    agent_version: str
    name: str
    reason: str
    score: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": str(self.agent_id),
            "agent_version": self.agent_version,
            "name": self.name,
            "reason": self.reason,
            "score": self.score,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> AgentCandidate:
        return cls(
            agent_id=UUID(str(raw["agent_id"])),
            agent_version=str(raw.get("agent_version") or ""),
            name=str(raw.get("name") or ""),
            reason=str(raw.get("reason") or ""),
            score=float(raw.get("score") or 0.0),
        )


@dataclass(frozen=True, slots=True)
class AgentTarget:
    """被选中的 agent 及其版本绑定。

    ``agent_version`` 一起带上 —— 会话**中途换 agent 版本**会让历史上下文的
    解释方式突变（与 §3.1 规则 1 的粘性理由同源）。
    """

    agent_id: UUID
    agent_version: str
    name: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": str(self.agent_id),
            "agent_version": self.agent_version,
            "name": self.name,
        }


@dataclass(frozen=True, slots=True)
class RouteDecision:
    """一次路由的完整留痕（§3.2 的定义）。

    ⚠️ ``source`` 决定**是哪条规则**命中的；``overridden_agent_id`` 在
    **粘性压过显式指定**时记下被压掉的那个 —— 否则用户「换个 agent 重新问」
    会发现没生效，且事后无从解释（§3.1 的备注）。
    """

    agent_id: UUID
    agent_version: str
    strategy_id: str
    rule_version: str
    confidence: float
    reason: str
    candidates: tuple[AgentCandidate, ...] = ()
    source: RouteSource = "fallback"
    overridden_agent_id: UUID | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": str(self.agent_id),
            "agent_version": self.agent_version,
            "strategy_id": self.strategy_id,
            "rule_version": self.rule_version,
            "confidence": self.confidence,
            "reason": self.reason,
            "candidates": [c.to_dict() for c in self.candidates],
            "source": self.source,
            "overridden_agent_id": (
                str(self.overridden_agent_id) if self.overridden_agent_id else None
            ),
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> RouteDecision:
        return cls(
            agent_id=UUID(str(raw["agent_id"])),
            agent_version=str(raw.get("agent_version") or ""),
            strategy_id=str(raw.get("strategy_id") or ""),
            rule_version=str(raw.get("rule_version") or ""),
            confidence=float(raw.get("confidence") or 0.0),
            reason=str(raw.get("reason") or ""),
            candidates=tuple(AgentCandidate.from_dict(c) for c in raw.get("candidates") or ()),
            source=raw.get("source") or "fallback",
            overridden_agent_id=(
                UUID(str(raw["overridden_agent_id"])) if raw.get("overridden_agent_id") else None
            ),
        )

    @property
    def target(self) -> AgentTarget:
        return AgentTarget(
            agent_id=self.agent_id,
            agent_version=self.agent_version,
            name=self.candidates[0].name if self.candidates else "",
        )


@dataclass(frozen=True, slots=True)
class SessionAssignment:
    """Router 给 Session 的落位（§9 的 ``Router → Session`` 契约）。

    ⚠️ Stage 1 还不产出它（会话路由归 Stage 2）—— 但**形状先定稿**，
    免得 Stage 2 又改一次接口。
    """

    session_ref: UUID
    agent_id: UUID
    agent_version: str
    ingress_seq: int = 0
    predecessor_seq: int = 0
    queue_position: int = 0


@dataclass(frozen=True, slots=True)
class RoutingAgent:
    """候选池里的一个 agent —— **策略配置的载体**（§3.3）。

    字段刻意与 ``admin_agents`` 的列一一对应：策略不新建表，配置就是
    agent 自己的属性。
    """

    agent_id: UUID
    agent_version: str
    name: str
    category: str = ""
    visible_scope: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    profile: Mapping[str, Any] = field(default_factory=dict)
    status: str = "published"

    @property
    def routing_profile(self) -> Mapping[str, Any]:
        """``profile["routing"]`` —— 策略专属的那一段配置。"""
        raw = self.profile.get("routing")
        return raw if isinstance(raw, Mapping) else {}

    @property
    def is_default(self) -> bool:
        """是不是兜底默认 agent（规则 5）。"""
        return bool(self.routing_profile.get("default"))

    @property
    def priority(self) -> float:
        """同一条规则内的排序优先级（越大越优先）。"""
        try:
            return float(self.routing_profile.get("priority") or 0)
        except (TypeError, ValueError):
            return 0.0

    @property
    def business_lines(self) -> tuple[str, ...]:
        """该 agent 服务的业务线 —— ``category`` + ``profile.routing.business_lines``。"""
        extra = self.routing_profile.get("business_lines") or ()
        if isinstance(extra, str):
            extra = (extra,)
        lines = [self.category] if self.category else []
        lines.extend(str(item) for item in extra)
        return tuple(lines)

    @property
    def routing_tags(self) -> tuple[str, ...]:
        """该 agent 命中的用户标签 —— ``tags`` + ``profile.routing.tags``。"""
        extra = self.routing_profile.get("tags") or ()
        if isinstance(extra, str):
            extra = (extra,)
        merged = list(self.tags)
        merged.extend(str(item) for item in extra)
        return tuple(merged)


@dataclass(frozen=True, slots=True)
class UserAttributes:
    """用户的可查询属性（§1.5 的 ``UserDirectoryPort`` 返回值）。

    ⚠️ 现状：**部门没有结构化字段** —— identity 的 ``User.metadata`` 是自由
    格式 JSONB，``ActorContext.roles`` 只有 JWT 里的 roles。这里把两者
    归一成一个形状，让 Strategy 不必知道数据从哪来。
    """

    departments: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    roles: frozenset[str] = frozenset()

    def all_values(self) -> frozenset[str]:
        return frozenset(self.departments) | frozenset(self.tags) | self.roles


@dataclass(frozen=True, slots=True)
class RoutingRequest:
    """一次路由请求。

    ⚠️ ``sticky_agent`` 是**粘性规则（规则 1）的唯一输入来源** —— 它由
    Session 的只读 ``lookup(session_key)`` 端口提供（§2 的两步流程）。
    Stage 1 还没有那个端口 → 粘性分支暂时拿不到输入，**规则本身已实现**。
    """

    tenant_id: UUID
    workspace_id: UUID
    user_id: UUID
    explicit_agent_id: UUID | None = None
    sticky_agent: AgentTarget | None = None
    roles: frozenset[str] = frozenset()
    business_line: str | None = None


@runtime_checkable
class AgentCatalogPort(Protocol):
    """Router 读 agent 目录的端口（§9 的 ``Router ← Agent Catalog``）。

    实现方复用既有的 ``AgentCatalogService`` —— **不另起一套查询**。
    """

    async def list_agents(
        self, *, tenant_id: UUID, workspace_id: UUID
    ) -> tuple[RoutingAgent, ...]: ...


@runtime_checkable
class UserDirectoryPort(Protocol):
    """Router 读用户属性的端口（§9 的 ``Router ← Identity``）。

    由 identity 模块提供实现 —— 把「用户属性」变成**可查询的数据**，
    而不是散落的 JSONB 约定（§1.5）。
    """

    async def get_user_attributes(self, *, tenant_id: UUID, user_id: UUID) -> UserAttributes: ...
