"""Agent runtime domain types.

Domain code MUST NOT import any framework / ORM / transport. All I/O is
expressed through ports (defined in application/ports/).
"""

from qzdap_kernel.events import DomainEvent

from qzdap.modules.agent_runtime.domain.entities import (
    Session,
    SessionStatus,
    Turn,
    TurnStatus,
)
from qzdap.modules.agent_runtime.domain.events import (
    SessionClosed,
    SessionOpened,
    TurnCompleted,
    TurnFailed,
    TurnStarted,
)

__all__ = [
    "DomainEvent",
    "Session",
    "SessionClosed",
    "SessionOpened",
    "SessionStatus",
    "Turn",
    "TurnCompleted",
    "TurnFailed",
    "TurnStarted",
    "TurnStatus",
]
