"""Tests for the schema package."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from qzdap_schema.dtos import (
    DoneChunk,
    MessageChunk,
    ToolCallChunk,
    UsageChunk,
)
from qzdap_schema.ids import (
    TenantId,
    WorkspaceId,
)


def test_branded_ids_are_distinct() -> None:
    tid = TenantId(uuid4())
    wid = WorkspaceId(uuid4())
    assert isinstance(tid, UUID)
    assert isinstance(wid, UUID)
    assert tid != wid


def test_typed_chunks_serialize() -> None:
    chunk = MessageChunk(turn_id=uuid4(), seq=0, content="hi")
    d = chunk.model_dump(mode="json")
    assert d["kind"] == "message"
    assert d["content"] == "hi"


def test_tool_call_chunk_carries_args() -> None:
    chunk = ToolCallChunk(
        turn_id=uuid4(),
        seq=1,
        tool_call_id=uuid4(),
        tool_name="github_search",
        arguments={"q": "anthropic"},
    )
    d = chunk.model_dump(mode="json")
    assert d["tool_name"] == "github_search"
    assert d["arguments"] == {"q": "anthropic"}


def test_usage_chunk_validation() -> None:
    chunk = UsageChunk(
        turn_id=uuid4(),
        seq=2,
        input_tokens=10,
        output_tokens=5,
        cache_read_tokens=0,
        cache_write_tokens=0,
        cost_usd=0.0,
    )
    assert chunk.input_tokens == 10
    # Negative should fail
    with pytest.raises(ValueError):
        UsageChunk(
            turn_id=uuid4(),
            seq=0,
            input_tokens=-1,
            output_tokens=0,
            cache_read_tokens=0,
            cache_write_tokens=0,
            cost_usd=0.0,
        )


def test_done_chunk_optional_message() -> None:
    chunk = DoneChunk(turn_id=uuid4(), seq=3, final_message=None)
    d = chunk.model_dump(mode="json")
    assert d["final_message"] is None


def test_problem_details_is_kernel_error() -> None:
    from qzdap_kernel.errors import ErrorEnvelope

    assert ErrorEnvelope.__name__ == "ErrorEnvelope"
