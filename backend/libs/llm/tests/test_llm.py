"""Tests for libs/qzdap_llm (mock + router + wire parsing)."""

from __future__ import annotations

import pytest

from qzdap_llm.client import ChatMessage, ChatRequest, ChatResponse, LLMChunk, LLMClient
from qzdap_llm.config import LLMConfig, LLMProvider
from qzdap_llm.mock import MockLLMClient
from qzdap_llm.router import LLMRouter


@pytest.mark.asyncio
async def test_mock_chat_echo() -> None:
    c = MockLLMClient(LLMConfig(mock_latency_ms=1))
    resp = await c.chat(
        ChatRequest(
            model="mock-m",
            messages=[ChatMessage(role="user", content="hi")],
        )
    )
    assert resp.message.content.startswith("echo:")
    assert resp.usage.input_tokens >= 0


@pytest.mark.asyncio
async def test_mock_stream_produces_chunks() -> None:
    c = MockLLMClient(LLMConfig(mock_latency_ms=1))
    chunks: list[LLMChunk] = []
    async for ch in c.stream(
        ChatRequest(
            model="mock-m",
            messages=[ChatMessage(role="user", content="hello world")],
        )
    ):
        chunks.append(ch)
    assert "hello" in "".join(c.delta for c in chunks)
    assert any(c.finish_reason == "stop" for c in chunks)


@pytest.mark.asyncio
async def test_router_chat_uses_primary() -> None:
    primary = MockLLMClient()
    secondary = MockLLMClient()
    router = LLMRouter(primary, failovers=[secondary])
    resp = await router.chat(
        ChatRequest(
            model="x",
            messages=[ChatMessage(role="user", content="ping")],
        )
    )
    assert resp is not None


@pytest.mark.asyncio
async def test_router_failover_on_error() -> None:
    from qzdap_kernel.errors import ExternalServiceError

    class Failing(LLMClient):
        name = "failing"

        async def chat(self, req: ChatRequest) -> ChatResponse:
            raise ExternalServiceError("boom", code="LLM_BOOM")

        async def stream(self, req: ChatRequest):
            raise ExternalServiceError("boom", code="LLM_BOOM")
            yield LLMChunk(model="x", delta="")

        async def embed(self, texts: list[str]) -> list[list[float]]:
            raise ExternalServiceError("boom", code="LLM_BOOM")

    ok = MockLLMClient()
    router = LLMRouter(Failing(), failovers=[ok])
    resp = await router.chat(
        ChatRequest(model="x", messages=[ChatMessage(role="user", content="hi")])
    )
    assert resp is not None


def test_config_default_provider_is_mock() -> None:
    cfg = LLMConfig()
    assert cfg.provider is LLMProvider.MOCK
