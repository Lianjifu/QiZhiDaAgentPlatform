"""LLM wire types (chat, streaming, embeddings)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Literal

Role = Literal["system", "user", "assistant", "tool"]


@dataclass(slots=True, frozen=True)
class ChatMessage:
    role: Role
    content: str
    name: str | None = None
    tool_call_id: str | None = None
    tool_calls: list[dict] | None = None


@dataclass(slots=True)
class ChatRequest:
    model: str
    messages: list[ChatMessage]
    temperature: float = 1.0
    max_tokens: int | None = None
    top_p: float | None = None
    stop: list[str] | None = None
    tools: list[dict] | None = None
    tool_choice: str | dict | None = None
    response_format: dict | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    trace_id: str | None = None


@dataclass(slots=True, frozen=True)
class Usage:
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0


@dataclass(slots=True, frozen=True)
class ChatResponse:
    model: str
    message: ChatMessage
    finish_reason: str
    usage: Usage
    raw: dict = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class LLMChunk:
    """A single streaming chunk. `delta` is content delta, may be empty."""

    model: str
    delta: str
    finish_reason: str | None = None
    tool_calls: list[dict] | None = None
    usage: Usage | None = None


class LLMClient:
    """Base protocol. Subclassed for each provider."""

    name: str = "base"

    async def chat(self, req: ChatRequest) -> ChatResponse:  # pragma: no cover
        raise NotImplementedError

    async def stream(
        self, req: ChatRequest
    ) -> AsyncIterator[LLMChunk]:  # pragma: no cover
        raise NotImplementedError
        yield

    async def embed(self, texts: list[str]) -> list[list[float]]:  # pragma: no cover
        raise NotImplementedError
