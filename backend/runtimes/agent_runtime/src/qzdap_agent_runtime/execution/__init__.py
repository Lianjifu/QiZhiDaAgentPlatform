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

__all__ = [
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
    "ToolCallRecord",
    "ToolFunction",
    "ToolRateLimitError",
    "ToolTimeoutError",
    "usage_from_chunks",
]