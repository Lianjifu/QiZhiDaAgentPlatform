"""Domain errors for the agent runtime.

Subclasses of `qzdap_kernel.errors.AppError`. Code/status are stable
wire-level identifiers the HTTP layer passes through to the client.

Governance errors (`ActionDeniedError`, `ApprovalRequiredError`) are
defined in `qzdap_kernel.errors` and re-exported here for module-local
import convenience.
"""

from __future__ import annotations

from typing import Any

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

    ⚠️ **重复请求不是错误**（Gateway 方案 §4.5）：命中重复时，正确行为是
    「重放上一轮事件流」；``session_events`` 真写真读就绪之前（Stage 4b），
    降级为「**202 + 上次 turn_id + ``replay_unavailable``**」。
    **不得静默丢弃重复请求。**
    """

    code = "DUPLICATE_REQUEST"
    status = 409

    def __init__(
        self,
        message: str = "",
        *,
        code: str | None = None,
        turn_id: Any = None,
        replay_unavailable: bool = True,
    ) -> None:
        super().__init__(
            message or "duplicate request",
            code=code or self.code,
            details=(
                {"turn_id": str(turn_id), "replay_unavailable": replay_unavailable}
                if turn_id is not None
                else {"replay_unavailable": replay_unavailable}
            ),
        )
        self.turn_id = turn_id
        self.replay_unavailable = replay_unavailable


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
