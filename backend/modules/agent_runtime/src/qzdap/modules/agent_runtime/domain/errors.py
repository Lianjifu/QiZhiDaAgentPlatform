"""Domain errors for the agent runtime.

Subclasses of `qzdap_kernel.errors.AppError`. Code/status are stable
wire-level identifiers the HTTP layer passes through to the client.

Governance errors (`ActionDeniedError`, `ApprovalRequiredError`) are
defined in `qzdap_kernel.errors` and re-exported here for module-local
import convenience.
"""

from __future__ import annotations

from qzdap_kernel.errors import (
    ActionDeniedError,
    AppError,
    ApprovalRequiredError,
    NotFoundError,
)


class SessionNotFound(NotFoundError):
    code = "SESSION_NOT_FOUND"


class TurnNotFound(NotFoundError):
    code = "TURN_NOT_FOUND"


class SessionClosedError(AppError):
    """Raised when a turn is attempted on a closed session."""

    code = "SESSION_CLOSED"
    status = 410


__all__ = [
    "ActionDeniedError",
    "ApprovalRequiredError",
    "SessionClosedError",
    "SessionNotFound",
    "TurnNotFound",
]
