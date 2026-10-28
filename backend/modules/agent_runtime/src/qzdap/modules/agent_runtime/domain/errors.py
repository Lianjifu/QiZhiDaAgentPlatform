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


class DuplicateRequestError(AppError):
    """Raised when a client request id is replayed on the same session.

    The frontend sends a fresh id per send; a repeat means a double click
    or a network retry, and must not start a second turn.
    """

    code = "DUPLICATE_REQUEST"
    status = 409


class SessionBusyError(AppError):
    """Raised when a second turn is started while one is still in flight.

    Concurrent turns on one session interleave their messages and race on
    the message sequence number, so the second one is rejected instead.
    """

    code = "SESSION_BUSY"
    status = 409


__all__ = [
    "ActionDeniedError",
    "ApprovalRequiredError",
    "DuplicateRequestError",
    "SessionBusyError",
    "SessionClosedError",
    "SessionNotFound",
    "TurnNotFound",
]
