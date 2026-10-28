"""SSE encoder — wraps a `TurnChunk` async iterator as a byte stream
emitting `event: <kind>\\ndata: <json>\\n\\n` per chunk plus a trailing
`event: end\\ndata: {}\\n\\n` terminator.

The HTTP layer wraps this in `StreamingResponse(media_type="text/event-stream")`.
We avoid pulling `sse-starlette` to keep the dependency surface tight.

While a turn is waiting on a slow tool or a slow model, no chunk is produced
for a while. The ingress in front of the app (`proxy_read_timeout 60s`) drops
connections that stay silent that long, which would truncate the answer
mid-flight. So we emit an SSE comment (`: keepalive`) on an idle stream:
it is a legal SSE frame that clients ignore, but it keeps the socket warm.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import suppress

from qzdap_schema.dtos.turn import TurnChunk

DEFAULT_KEEPALIVE_SECONDS = 15.0


async def sse_stream(
    chunks: AsyncIterator[TurnChunk],
    *,
    keepalive_seconds: float = DEFAULT_KEEPALIVE_SECONDS,
) -> AsyncIterator[bytes]:
    """Encode chunks as SSE, emitting a keepalive frame while idle."""
    iterator = chunks.__aiter__()
    pending: asyncio.Task | None = None
    try:
        while True:
            if pending is None:
                pending = asyncio.ensure_future(iterator.__anext__())
            done, _pending = await asyncio.wait(
                {pending}, timeout=keepalive_seconds
            )
            if not done:
                # Still waiting for the next chunk — tell the proxy we're alive.
                yield b": keepalive\n\n"
                continue
            task, pending = pending, None
            try:
                chunk = task.result()
            except StopAsyncIteration:
                break
            yield f"event: {chunk.kind}\ndata: {chunk.model_dump_json()}\n\n".encode()
        yield b"event: end\ndata: {}\n\n"
    finally:
        if pending is not None:
            pending.cancel()
            with suppress(BaseException):
                await pending
        aclose = getattr(iterator, "aclose", None)
        if aclose is not None:
            with suppress(BaseException):
                await aclose()


__all__ = ["DEFAULT_KEEPALIVE_SECONDS", "sse_stream"]
