"""Simple in-memory token bucket rate limit (per minute).

Production should swap this for a Redis-backed implementation; the API is
the same.
"""

from __future__ import annotations

import time
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from qzdap_kernel.errors import RateLimitError


@dataclass(slots=True, frozen=True)
class RateLimitPolicy:
    requests_per_minute: int
    window_seconds: int = 60


class RateLimitMiddleware:
    def __init__(self, app: Callable, *, policy: RateLimitPolicy) -> None:
        self.app = app
        self.policy = policy
        self._buckets: dict[str, tuple[int, float]] = defaultdict(lambda: (0, 0.0))

    async def __call__(self, scope: dict, receive: Callable, send: Callable) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Bucket key = tenant_id if available, else remote address
        key = self._bucket_key(scope)
        now = time.time()
        count, reset = self._buckets[key]
        if now - reset >= self.policy.window_seconds:
            count, reset = 0, now
        if count >= self.policy.requests_per_minute:
            await send(
                {
                    "type": "http.response.start",
                    "status": 429,
                    "headers": [(b"content-type", b"application/json")],
                }
            )
            await send(
                {
                    "type": "http.response.body",
                    "body": b'{"code":"RATE_LIMITED"}',
                }
            )
            return
        self._buckets[key] = (count + 1, reset)
        await self.app(scope, receive, send)

    def _bucket_key(self, scope: dict) -> str:
        st = scope.get("state") or {}
        if tid := st.get("tenant_id"):
            return f"tenant:{tid}"
        host, _ = scope.get("client", ("?", 0))
        return f"ip:{host}"


async def rate_limit_dependency(
    request: object,  # FastAPI Request
    _next: Callable[[object], Awaitable[object]],
) -> object:
    """Marker dependency — actual rate limiting happens in middleware."""
    return _next


# Re-export the error so callers can raise it from UseCases if they want to
__all__ = ["RateLimitError", "RateLimitMiddleware", "RateLimitPolicy"]
