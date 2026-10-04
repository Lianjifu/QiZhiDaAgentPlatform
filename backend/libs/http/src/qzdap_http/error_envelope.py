"""RFC-9457-style error envelope middleware.

Any uncaught exception raised by a downstream handler is converted into a
JSON envelope with the canonical shape. AppError subclasses keep their
status; everything else becomes 500.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable

from qzdap_kernel.contextvars import current_trace_id
from qzdap_kernel.errors import AppError, InternalError
from qzdap_observability.logging import get_logger

_log = get_logger("http.error")


async def error_envelope_middleware(
    request: object,
    call_next: Callable[[object], Awaitable[object]],
) -> object:
    try:
        return await call_next(request)
    except AppError as e:
        env = e.to_envelope(trace_id=current_trace_id())
        _log.warning("app.error", code=env.code, message=env.message, status=env.status)
        return _json_response(env.to_dict(), env.status)
    except Exception:  # noqa: BLE001
        _log.exception("unhandled.exception")
        env = InternalError("internal error", code="INTERNAL_ERROR").to_envelope(
            trace_id=current_trace_id()
        )
        return _json_response(env.to_dict(), 500)


def _json_response(payload: dict, status: int) -> object:
    from starlette.responses import JSONResponse

    return JSONResponse(content=payload, status_code=status)


def _json_dumps(payload: dict) -> str:
    return json.dumps(payload, default=str)
