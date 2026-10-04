"""Async-safe trace-id context variable.

The trace-id is set by the HTTP middleware at request entry, consumed by every
logger / OTel span / SSE chunk that wants to be correlatable.
"""

from __future__ import annotations

import uuid
from contextvars import ContextVar

trace_id_var: ContextVar[str | None] = ContextVar("qzdap_trace_id", default=None)


def new_trace_id() -> str:
    """Generate a new trace id (32-char hex, no dashes)."""
    return uuid.uuid4().hex


def current_trace_id() -> str | None:
    """Return the trace-id bound to the current task, or None if unset."""
    return trace_id_var.get()


def bind_trace_id(trace_id: str | None = None) -> str:
    """Bind a trace id (generate if absent) and return it.

    Returns the trace id (NOT a Token) — for use by loggers/metrics. Use
    `bind_trace_id_token` if you need a `Token` to reset later.
    """
    if trace_id is None:
        trace_id = new_trace_id()
    trace_id_var.set(trace_id)
    return trace_id


def bind_trace_id_token(trace_id: str | None = None) -> tuple[str, object]:
    """Bind a trace id and return `(trace_id, token)` for symmetric reset."""
    if trace_id is None:
        trace_id = new_trace_id()
    token = trace_id_var.set(trace_id)
    return trace_id, token


def reset_trace_id(token: object) -> None:
    """Reset the trace-id context var to its previous value."""
    trace_id_var.reset(token)  # type: ignore[arg-type]
