"""SSE encoder — wraps a `TurnChunk` async iterator as a byte stream
emitting `event: <kind>\\ndata: <json>\\n\\n` per chunk plus a trailing
`event: end\\ndata: {}\\n\\n` terminator.

The HTTP layer wraps this in `StreamingResponse(media_type="text/event-stream")`.
We avoid pulling `sse-starlette` to keep the dependency surface tight.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from qzdap_schema.dtos.turn import TurnChunk


async def sse_stream(chunks: AsyncIterator[TurnChunk]) -> AsyncIterator[bytes]:
    async for chunk in chunks:
        line = f"event: {chunk.kind}\ndata: {chunk.model_dump_json()}\n\n"
        yield line.encode("utf-8")
    yield b"event: end\ndata: {}\n\n"
