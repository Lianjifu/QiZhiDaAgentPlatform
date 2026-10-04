"""In-memory mock LLM for dev + tests.

Deterministic echo with a configurable latency. Used by `MockLLMClient`.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from qzdap_llm.client import (
    ChatMessage,
    ChatRequest,
    ChatResponse,
    LLMChunk,
    LLMClient,
    Usage,
)
from qzdap_llm.config import LLMConfig


class MockLLMClient(LLMClient):
    name = "mock"

    def __init__(self, config: LLMConfig | None = None) -> None:
        self._cfg = config or LLMConfig()

    async def chat(self, req: ChatRequest) -> ChatResponse:
        await asyncio.sleep(self._cfg.mock_latency_ms / 1000)
        content = _mock_response_text(req.messages)
        return ChatResponse(
            model=req.model,
            message=ChatMessage(role="assistant", content=content),
            finish_reason="stop",
            usage=Usage(input_tokens=10, output_tokens=len(content) // 4),
            raw={"mock": True},
        )

    async def stream(self, req: ChatRequest) -> AsyncIterator[LLMChunk]:
        content = _mock_response_text(req.messages)
        for i, word in enumerate(content.split(" ")):
            await asyncio.sleep(
                self._cfg.mock_latency_ms / 1000 / max(len(content.split(" ")), 1)
            )
            yield LLMChunk(model=req.model, delta=word + " ")
        yield LLMChunk(model=req.model, delta="", finish_reason="stop")

    async def embed(self, texts: list[str]) -> list[list[float]]:
        # Deterministic pseudo-embedding from text hash. NOT real semantics;
        # for tests only.
        out: list[list[float]] = []
        for t in texts:
            seed = abs(hash(t)) % (2**32)
            v = [(seed >> i & 0xFF) / 255.0 for i in range(8)]
            out.append(v + [0.0] * (self._cfg.embedding_dim - 8))
        return out


def _mock_response_text(messages: list[ChatMessage]) -> str:
    user = next((m for m in reversed(messages) if m.role == "user"), None)
    body = (user.content if user else "hello").strip()
    return f"echo: {body}"
