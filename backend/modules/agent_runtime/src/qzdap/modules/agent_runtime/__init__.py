"""Agent runtime — sessions, turns, LLM streaming, SSE.

Public surface re-exports the most common domain types so route / service
callers can `from qzdap.modules.agent_runtime import Session, Turn, ...`.
"""

from qzdap.modules.agent_runtime.application.services import AgentRuntimeService
from qzdap.modules.agent_runtime.domain import (
    DomainEvent,
    Session,
    SessionClosed,
    SessionOpened,
    SessionStatus,
    Turn,
    TurnCompleted,
    TurnFailed,
    TurnStarted,
    TurnStatus,
)
from qzdap.modules.agent_runtime.domain.errors import (
    ActionDeniedError,
    ApprovalRequiredError,
    SessionClosedError,
    SessionNotFound,
    TurnNotFound,
)

__all__ = [
    "ActionDeniedError",
    "AgentRuntimeService",
    "ApprovalRequiredError",
    "DomainEvent",
    "Session",
    "SessionClosed",
    "SessionClosedError",
    "SessionNotFound",
    "SessionOpened",
    "SessionStatus",
    "Turn",
    "TurnCompleted",
    "TurnFailed",
    "TurnNotFound",
    "TurnStarted",
    "TurnStatus",
]
