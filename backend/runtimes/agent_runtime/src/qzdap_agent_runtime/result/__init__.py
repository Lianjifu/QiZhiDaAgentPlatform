"""Result 层：内部事件类型 ✓（⚠️ **对外契约只有前端那一套** ✓）。

⚠️ **事件类型有两套** ✓ —— 本模块的是**内部**的 ✓（出站编码器在用 ✓），
**前端契约**是 ``libs/schema/dtos/turn.py`` 的 ``TurnChunk`` ✓
（关注点 #24 ✓ —— 两套并存归 Agent Stage 7 收口 ✓）。
"""

from __future__ import annotations

from .events import (
    ApprovalRequiredEvent,
    ContextCompactedEvent,
    DoneEvent,
    ErrorEvent,
    EventKind,
    KnowledgeSearchEvent,
    MemoryWriteEvent,
    MessageEvent,
    ResultEvent,
    SkillInvocationEvent,
    ToolCallEvent,
    ToolResultEvent,
    UsageEvent,
)

__all__ = [
    "ApprovalRequiredEvent",
    "ContextCompactedEvent",
    "DoneEvent",
    "ErrorEvent",
    "EventKind",
    "KnowledgeSearchEvent",
    "MemoryWriteEvent",
    "MessageEvent",
    "ResultEvent",
    "SkillInvocationEvent",
    "ToolCallEvent",
    "ToolResultEvent",
    "UsageEvent",
]
