"""Router 层 —— 会话路由（**选出 agent**）。

Router 方案（``docs/refactor/session-architecture/router-refactor-plan.md``）：
Gateway → Router → Session。Router 只做两件事：**派生会话 key** 与
**选出 agent** —— 不碰会话生命周期、不装上下文、不调 LLM。

**这一层是契约层** —— 不引框架、不引模块
（架构测试 ``backend/tests/architecture/test_router_boundary.py`` 守着这条线）。

阶段进度：Stage 0（契约与配置）+ Stage 1（Strategy 落地 web 路径）。
会话 key 派生（Stage 2）与 FIFO 放行（Stage 3）的契约**不提前建**
—— 没有调用方的类型就是「建而不切」。
"""

from qzdap_agent_runtime.router.strategy import RuleChainStrategy, Strategy
from qzdap_agent_runtime.router.types import (
    RULE_VERSION,
    STRATEGY_ID,
    AgentCandidate,
    AgentCatalogPort,
    AgentTarget,
    RouteDecision,
    RoutingAgent,
    RoutingRequest,
    RoutingUnavailable,
    SessionAssignment,
    UserAttributes,
    UserDirectoryPort,
)

__all__ = [
    "RULE_VERSION",
    "STRATEGY_ID",
    "AgentCandidate",
    "AgentCatalogPort",
    "AgentTarget",
    "RouteDecision",
    "RoutingAgent",
    "RoutingRequest",
    "RoutingUnavailable",
    "RuleChainStrategy",
    "SessionAssignment",
    "Strategy",
    "UserAttributes",
    "UserDirectoryPort",
]
