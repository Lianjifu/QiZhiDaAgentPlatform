"""SSE encoder — wraps a `TurnChunk` async iterator as a byte stream
emitting `id: <seq>\\nevent: <kind>\\ndata: <json>\\n\\n` per chunk plus a
trailing `event: end\\ndata: {}\\n\\n` terminator.

The HTTP layer wraps this in `StreamingResponse(media_type="text/event-stream")`.
We avoid pulling `sse-starlette` to keep the dependency surface tight.

**`id:` 是断线续传的游标**（Gateway 方案 §4.5）：它等于事件的 ``seq``
（``session_events.seq``），客户端重连时把它作为 ``Last-Event-ID`` 带回来，
服务端据此只重放它**之后**的那几段。

While a turn is waiting on a slow tool or a slow model, no chunk is produced
for a while. The ingress in front of the app (`proxy_read_timeout 60s`) drops
connections that stay silent that long, which would truncate the answer
mid-flight. So we emit an SSE comment (`: keepalive`) on an idle stream:
it is a legal SSE frame that clients ignore, but it keeps the socket warm.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import suppress
from typing import TYPE_CHECKING

from qzdap_schema.dtos.turn import TurnChunk

if TYPE_CHECKING:
    from qzdap_agent_runtime.gateway.replay import StoredEvent

DEFAULT_KEEPALIVE_SECONDS = 15.0


def sse_frame(*, seq: int, event_type: str, data: str) -> bytes:
    """一帧 SSE —— ``id`` / ``event`` / ``data`` 三个字段。

    **live 与 replay 共用这一个编码器** —— 重放出来的帧与原始帧同形，
    客户端不需要区分「这是重放的」。
    """
    return f"id: {seq}\nevent: {event_type}\ndata: {data}\n\n".encode()


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
            done, _pending = await asyncio.wait({pending}, timeout=keepalive_seconds)
            if not done:
                # Still waiting for the next chunk — tell the proxy we're alive.
                yield b": keepalive\n\n"
                continue
            task, pending = pending, None
            try:
                chunk = task.result()
            except StopAsyncIteration:
                break
            yield sse_frame(
                seq=int(chunk.seq),
                event_type=str(chunk.kind),
                data=chunk.model_dump_json(),
            )
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


async def sse_replay(events: list[StoredEvent]) -> AsyncIterator[bytes]:
    """重放已落库的事件 —— **与 live 同形**（含 ``id:``）。

    载荷用 ``json.dumps`` 而不是 pydantic 的序列化：``session_events.payload``
    是 JSONB，**不保序**（PostgreSQL 会重排键），因此重放出来的字节流与原始
    字节流**不会逐字节相同** —— 但语义相同（JSON 对象的键序无关），
    一致性校验也比的是**规范化后**的摘要（``event_digest``）。
    """
    for event in events:
        yield sse_frame(
            seq=int(event.seq),
            event_type=str(event.event_type),
            data=json.dumps(event.payload, separators=(",", ":"), ensure_ascii=False),
        )
    yield b"event: end\ndata: {}\n\n"


__all__ = ["DEFAULT_KEEPALIVE_SECONDS", "sse_frame", "sse_replay", "sse_stream"]
