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
from qzdap_schema.dtos.errors import project_error_message

_log = get_logger("http.error")


async def error_envelope_middleware(
    request: object,
    call_next: Callable[[object], Awaitable[object]],
) -> object:
    try:
        return await call_next(request)
    except AppError as e:
        env = e.to_envelope(trace_id=current_trace_id())
        # 没有自定义消息 → 用**投影文案**代替裸码（裸码对调用方毫无意义；
        # 日志里另有 code 字段 ✓）。有具体消息的一律保留。
        env.message = project_error_message(env.code, env.message, "http")
        _log.warning("app.error", code=env.code, message=env.message, status=env.status)
        return _json_response(env.to_dict(), env.status)
    except Exception:
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
