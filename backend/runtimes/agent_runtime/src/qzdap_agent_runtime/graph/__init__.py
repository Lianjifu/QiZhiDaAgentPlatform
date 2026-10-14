"""Graph 层：StateGraph 节点、routing、checkpoint。

§2.5 阻塞 6 决议：Stage 4 范围内仅实现 `classify_task_kind_heuristic`
（纯规则 fallback，不依赖任何模型）；Stage 6b 再接入小模型分类器。
"""

from __future__ import annotations

from .builder import build_session_graph
from .routing import (
    AgentRouteConfig,
    TaskKind,
    classify_task_kind_heuristic,
    is_deep_task,
)
from .state import (
    SCHEMA_VERSION,
    PendingApproval,
    ResultState,
    Route,
    RuntimeErrorState,
    SessionState,
    Todo,
    ToolCallState,
    ToolResultState,
    UsageState,
)

__all__ = [
    "AgentRouteConfig",
    "PendingApproval",
    "ResultState",
    "Route",
    "RuntimeErrorState",
    "SCHEMA_VERSION",
    "SessionState",
    "TaskKind",
    "Todo",
    "ToolCallState",
    "ToolResultState",
    "UsageState",
    "build_session_graph",
    "classify_task_kind_heuristic",
    "is_deep_task",
]