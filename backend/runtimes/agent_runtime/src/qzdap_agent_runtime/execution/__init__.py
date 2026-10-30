"""Execution 层：模型调用 ✓ / 工具绑定与执行 ✓（Agent 方案 §5 ✓）。

⚠️ **⑨ Execution Runtime** ✓（Agent 方案 §5 ✓）—— 模型解析 ✓ / 工具绑定与
执行 ✓ 都归这里 ✓（**不做选择** ✓ —— 决策 #4 ✓）。

⚠️ **这里没有第二个执行器** ✓ —— 幂等 ✓ / 重试 ✓ / 熔断都在
``modules/tool`` 的 ``InvokeToolUseCase`` 那一侧 ✓（唯一权威 ✓）——
本层只是**端口与装配** ✓。
"""

from __future__ import annotations

from .chat_model import QZDAPChatModel
from .llm_client import LLMCaller, ResolvedModel, usage_from_chunks
from .tool_binding import (
    RISK_ORDER,
    BindingPolicy,
    ToolBindingResolver,
    ToolExecutionError,
    ToolScope,
    current_actor,
    current_tool_scope,
    require_actor,
    reset_current_actor,
    reset_current_tool_scope,
    set_current_actor,
    set_current_tool_scope,
    tool_schema,
)

__all__ = [
    "RISK_ORDER",
    "BindingPolicy",
    "LLMCaller",
    "QZDAPChatModel",
    "ResolvedModel",
    "ToolBindingResolver",
    "ToolExecutionError",
    "ToolScope",
    "current_actor",
    "current_tool_scope",
    "require_actor",
    "reset_current_actor",
    "reset_current_tool_scope",
    "set_current_actor",
    "set_current_tool_scope",
    "tool_schema",
    "usage_from_chunks",
]
