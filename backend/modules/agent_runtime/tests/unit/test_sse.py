"""Unit tests for the SSE encoder."""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID

from qzdap_schema.dtos.turn import (
    DoneChunk,
    ErrorChunk,
    MessageChunk,
    UsageChunk,
)

from qzdap.modules.agent_runtime.adapter.http.sse import sse_stream


async def _gen() -> AsyncIterator:
    tid = UUID(int=1)
    yield MessageChunk(turn_id=tid, seq=1, content="hello ")
    yield MessageChunk(turn_id=tid, seq=2, content="world")
    yield UsageChunk(
        turn_id=tid,
        seq=3,
        input_tokens=4,
        output_tokens=5,
        cache_read_tokens=0,
        cache_write_tokens=0,
        cost_usd=0.0,
    )
    yield DoneChunk(turn_id=tid, seq=4, final_message="hello world")


async def test_sse_stream_emits_event_data_per_chunk() -> None:
    out = b""
    async for piece in sse_stream(_gen()):
        out += piece
    decoded = out.decode("utf-8")

    assert "event: message\n" in decoded
    assert "event: usage\n" in decoded
    assert "event: done\n" in decoded
    # Each non-terminal chunk: data line carries JSON.
    assert 'data: {"turn_id"' in decoded
    # Terminating marker
    assert decoded.rstrip().endswith("event: end\ndata: {}")


async def test_sse_stream_empty_generator_still_emits_end() -> None:
    async def empty() -> AsyncIterator:
        if False:
            yield
        return

    out = b""
    async for piece in sse_stream(empty()):
        out += piece
    assert out == b"event: end\ndata: {}\n\n"


async def test_sse_stream_round_trips_error_chunk() -> None:
    async def err() -> AsyncIterator:
        tid = UUID(int=2)
        yield ErrorChunk(
            turn_id=tid, seq=1, code="SESSION_CLOSED", message="closed", retriable=False
        )

    out = b""
    async for piece in sse_stream(err()):
        out += piece
    decoded = out.decode("utf-8")
    assert "event: error\n" in decoded
    assert "SESSION_CLOSED" in decoded
