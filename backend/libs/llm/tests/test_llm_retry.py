"""LLM 上游重试契约：瞬时错误才重试，流式吐过字就不重试。"""

from __future__ import annotations

import httpx
import pytest

from qzdap_llm import ChatMessage, ChatRequest, ProviderTransportError, RetryPolicy
from qzdap_llm.config import LLMConfig
from qzdap_llm.openai_compatible import OpenAICompatibleClient

CONFIG = LLMConfig(provider="custom", base_url="https://example.test/v1", api_key="k")


def _client(handler, *, policy: RetryPolicy) -> OpenAICompatibleClient:
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = OpenAICompatibleClient(CONFIG, http=http, retry_policy=policy)
    # ⚠️ 不真的等 —— 测试要能断言退避时长，而不是干等。
    client._sleep = _no_sleep
    return client


async def _no_sleep(_seconds: float) -> None:
    return None


REQUEST = ChatRequest(
    model="test-model",
    messages=[ChatMessage("user", "hi")],
)


def _ok_body() -> bytes:
    return b'{"model":"m","choices":[{"message":{"role":"assistant","content":"ok"},"finish_reason":"stop"}],"usage":{"input_tokens":1,"output_tokens":1}}'


@pytest.mark.asyncio
async def test_chat_retries_on_500_then_succeeds():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(500, json={"error": "boom"})
        return httpx.Response(200, content=_ok_body())

    client = _client(handler, policy=RetryPolicy(max_attempts=3, base_delay_seconds=0.01))
    resp = await client.chat(REQUEST)
    assert resp.message.content == "ok"
    assert calls["n"] == 3


@pytest.mark.asyncio
async def test_chat_does_not_retry_on_400():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(400, json={"error": "bad request"})

    client = _client(handler, policy=RetryPolicy(max_attempts=3, base_delay_seconds=0.01))
    with pytest.raises(ProviderTransportError):
        await client.chat(REQUEST)
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_chat_retries_on_connect_error():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 2:
            raise httpx.ConnectError("boom", request=request)
        return httpx.Response(200, content=_ok_body())

    client = _client(handler, policy=RetryPolicy(max_attempts=3, base_delay_seconds=0.01))
    resp = await client.chat(REQUEST)
    assert resp.message.content == "ok"
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_chat_gives_up_after_max_attempts():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        raise httpx.ReadTimeout("slow", request=request)

    client = _client(handler, policy=RetryPolicy(max_attempts=2, base_delay_seconds=0.01))
    with pytest.raises(ProviderTransportError):
        await client.chat(REQUEST)
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_retry_after_header_wins_over_backoff():
    delays: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"retry-after": "7"}, json={"error": "slow down"})

    client = _client(handler, policy=RetryPolicy(max_attempts=2, base_delay_seconds=0.01))

    async def record(seconds: float) -> None:
        delays.append(seconds)

    client._sleep = record
    with pytest.raises(ProviderTransportError):
        await client.chat(REQUEST)
    assert delays == [7.0]


@pytest.mark.asyncio
async def test_stream_retries_before_first_chunk():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 2:
            return httpx.Response(503, json={"error": "warming up"})
        body = b'data: {"choices":[{"delta":{"content":"hi"}}]}\n\ndata: [DONE]\n\n'
        return httpx.Response(200, content=body)

    client = _client(handler, policy=RetryPolicy(max_attempts=3, base_delay_seconds=0.01))
    chunks = [chunk async for chunk in client.stream(REQUEST)]
    assert calls["n"] == 2
    assert "".join(chunk.delta for chunk in chunks) == "hi"


@pytest.mark.asyncio
async def test_stream_does_not_retry_after_emitting_a_chunk():
    """⚠️ 吐过字之后上游断了 —— 只能中断，不能重放（会重复吐字）。"""
    calls = {"n": 0}

    class _BrokenStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b'data: {"choices":[{"delta":{"content":"partial"}}]}\n\n'
            raise httpx.ReadError("connection reset")

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            stream=_BrokenStream(),
        )

    client = _client(handler, policy=RetryPolicy(max_attempts=3, base_delay_seconds=0.01))
    seen: list[str] = []
    with pytest.raises(ProviderTransportError):
        async for chunk in client.stream(REQUEST):
            seen.append(chunk.delta)
    assert calls["n"] == 1
    assert seen == ["partial"]


def test_policy_rejects_invalid_values():
    with pytest.raises(ValueError):
        RetryPolicy(max_attempts=0)
    with pytest.raises(ValueError):
        RetryPolicy(jitter=1.5)


def test_delay_grows_exponentially_and_stays_bounded():
    policy = RetryPolicy(max_attempts=6, base_delay_seconds=1.0, max_delay_seconds=4.0, jitter=0.0)
    assert policy.delay_seconds(1) == 1.0
    assert policy.delay_seconds(2) == 2.0
    assert policy.delay_seconds(3) == 4.0
    assert policy.delay_seconds(4) == 4.0


def test_should_retry_classifies_status_codes():
    policy = RetryPolicy()
    assert policy.should_retry_status(429)
    assert policy.should_retry_status(503)
    assert not policy.should_retry_status(400)
    assert not policy.should_retry_status(401)
