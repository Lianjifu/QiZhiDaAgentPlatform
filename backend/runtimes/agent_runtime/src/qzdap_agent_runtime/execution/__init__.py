"""Execution 协议层：LockManager + ToolExecutor（§5.7 / §4.2 / §4.3 / §5.8）。

⚠️ **⑨ Execution Runtime** ✓（Agent 方案 §5 ✓）—— 模型解析 ✓ / 工具绑定与
执行 ✓ 都归这里 ✓（**不做选择** ✓ —— 决策 #4 ✓）。
"""

from __future__ import annotations

from .chat_model import QZDAPChatModel
from .executor import (
    InMemoryToolExecutor,
    ToolArgumentError,
    ToolCallRecord,
    ToolFunction,
    ToolRateLimitError,
    ToolTimeoutError,
)
from .llm_client import LLMCaller, ResolvedModel, usage_from_chunks
from .lock import (
    InMemoryLockManager,
    LockManager,
    LockToken,
    RevisionConflictError,
    SessionBusyError,
)
from .tool_binding import (
    RISK_ORDER,
    BindingPolicy,
    ToolBindingResolver,
    current_actor,
    require_actor,
    reset_current_actor,
    set_current_actor,
    tool_schema,
)

__all__ = [
    "RISK_ORDER",
    "BindingPolicy",
    "InMemoryLockManager",
    "InMemoryToolExecutor",
    "LLMCaller",
    "LockManager",
    "LockToken",
    "QZDAPChatModel",
    "ResolvedModel",
    "RevisionConflictError",
    "SessionBusyError",
    "ToolArgumentError",
    "ToolBindingResolver",
    "ToolCallRecord",
    "ToolFunction",
    "ToolRateLimitError",
    "ToolTimeoutError",
    "current_actor",
    "require_actor",
    "reset_current_actor",
    "set_current_actor",
    "tool_schema",
    "usage_from_chunks",
]