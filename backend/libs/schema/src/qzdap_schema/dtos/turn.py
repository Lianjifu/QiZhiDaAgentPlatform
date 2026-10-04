"""Turn stream chunk DTOs.

The agent_runtime streams turn progress over SSE as a sequence of
`TurnChunk` envelopes. Each chunk carries a `kind` field that the client uses
to dispatch rendering.
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

ChunkKind = Literal[
    "message",
    "tool_call",
    "tool_result",
    "skill_invocation",
    "memory_write",
    "knowledge_search",
    "approval_required",
    "context_compacted",
    "usage",
    "done",
    "error",
]


class ChunkEnvelope(BaseModel):
    """Wrapper around every chunk with shared metadata."""

    turn_id: UUID
    seq: int = Field(ge=0)
    kind: ChunkKind


class MessageChunk(ChunkEnvelope):
    kind: Literal["message"] = "message"
    content: str
    role: Literal["assistant"] = "assistant"


class ToolCallChunk(ChunkEnvelope):
    kind: Literal["tool_call"] = "tool_call"
    tool_call_id: UUID
    tool_name: str
    arguments: dict


class ToolResultChunk(ChunkEnvelope):
    kind: Literal["tool_result"] = "tool_result"
    tool_call_id: UUID
    output: str | dict
    is_error: bool = False
    latency_ms: int = Field(ge=0)


class SkillInvocationChunk(ChunkEnvelope):
    kind: Literal["skill_invocation"] = "skill_invocation"
    invocation_id: UUID
    skill_name: str
    status: Literal["started", "stream", "succeeded", "failed", "cancelled"]


class MemoryWriteChunk(ChunkEnvelope):
    kind: Literal["memory_write"] = "memory_write"
    layer: Literal["l1", "l2"] = "l1"
    preview: str = ""


class ApprovalRequiredChunk(ChunkEnvelope):
    kind: Literal["approval_required"] = "approval_required"
    approval_id: UUID
    tool_name: str
    arguments: dict = Field(default_factory=dict)
    reason: str = ""


class ContextCompactedChunk(ChunkEnvelope):
    kind: Literal["context_compacted"] = "context_compacted"
    tokens_before: int = Field(ge=0, default=0)
    tokens_after: int = Field(ge=0, default=0)


class UsageChunk(ChunkEnvelope):
    kind: Literal["usage"] = "usage"
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    cache_read_tokens: int = Field(ge=0)
    cache_write_tokens: int = Field(ge=0)
    cost_usd: float = Field(ge=0)


class DoneChunk(ChunkEnvelope):
    kind: Literal["done"] = "done"
    final_message: str | None = None


class ErrorChunk(ChunkEnvelope):
    kind: Literal["error"] = "error"
    code: str
    message: str
    retriable: bool = False


# Type union for client-side discriminated parsing
TurnChunk = (
    MessageChunk
    | ToolCallChunk
    | ToolResultChunk
    | SkillInvocationChunk
    | MemoryWriteChunk
    | ApprovalRequiredChunk
    | ContextCompactedChunk
    | UsageChunk
    | DoneChunk
    | ErrorChunk
)
