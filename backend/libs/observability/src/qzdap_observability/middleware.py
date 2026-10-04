"""HTTP middleware: log every request + record metrics + bind trace id."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable

from qzdap_kernel.contextvars import (
    bind_trace_id_token,
    current_trace_id,
    reset_trace_id,
)

from qzdap_observability.logging import get_logger
from qzdap_observability.metrics import record_http_request

_log = get_logger("http")


class ObservabilityMiddleware:
    """ASGI-compatible middleware.

    Records request duration + status. Binds a trace id into the context
    so downstream logger calls carry it.
    """

    def __init__(self, app: Callable) -> None:
        self.app = app

    async def __call__(self, scope: dict, receive: Callable, send: Callable) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start = time.perf_counter()
        trace_id_in = None
        for k, v in scope.get("headers") or []:
            if k == b"x-trace-id":
                trace_id_in = v.decode("latin1")
                break

        _, token = bind_trace_id_token(trace_id_in)
        method = scope.get("method", "GET")
        path = scope.get("path", "/")
        status_holder = {"code": 500}

        async def send_wrapper(message: dict) -> None:
            if message["type"] == "http.response.start":
                status_holder["code"] = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration = time.perf_counter() - start
            try:
                record_http_request(method, path, status_holder["code"], duration)
                _log.info(
                    "http.request",
                    method=method,
                    path=path,
                    status=status_holder["code"],
                    duration_ms=round(duration * 1000, 2),
                    trace_id=current_trace_id(),
                )
            finally:
                reset_trace_id(token)


# Async callable alias for FastAPI add_middleware
async def as_middleware_dispatch(
    request: object,
    call_next: Callable[[object], Awaitable[object]],
) -> object:
    return await call_next(request)
