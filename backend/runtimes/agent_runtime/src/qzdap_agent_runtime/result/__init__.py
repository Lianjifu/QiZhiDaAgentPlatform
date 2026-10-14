"""Result 协议层：ResultEvent 内部事件 + 与对外 TurnChunk 适配 + Sink 分发 (§3.2 / §5.9 / §13.5)。"""

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
    SkillInvocationEvent,
    ToolCallEvent,
    ToolResultEvent,
    UsageEvent,
    ResultEvent,
)
from .sink import (
    DispatchError,
    InMemoryResultSink,
    ResultDispatcher,
    ResultSink,
)

__all__ = [
    "ApprovalRequiredEvent",
    "ContextCompactedEvent",
    "DispatchError",
    "DoneEvent",
    "ErrorEvent",
    "EventKind",
    "InMemoryResultSink",
    "KnowledgeSearchEvent",
    "MemoryWriteEvent",
    "MessageEvent",
    "ResultDispatcher",
    "ResultEvent",
    "ResultSink",
    "SkillInvocationEvent",
    "ToolCallEvent",
    "ToolResultEvent",
    "UsageEvent",
]