"""Embedding adapter unit tests.

No-op is straightforward (zero vector). The HTTP and OpenAI adapters
delegate to ``httpx.AsyncClient``; we inject a mock client so no real
network calls happen.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from qzdap.modules.memory.adapter.embedding.http_adapter import HttpEmbeddingAdapter
from qzdap.modules.memory.adapter.embedding.noop_adapter import NoOpEmbedding
from qzdap.modules.memory.adapter.embedding.openai_adapter import OpenAIEmbeddingAdapter
from qzdap.modules.memory.domain.entities import EMBEDDING_DIM


def _fake_response(payload: dict[str, Any]) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = payload
    resp.raise_for_status = MagicMock()
    return resp


def _patch_client(adapter: Any, response: MagicMock) -> AsyncMock:
    """Replace the adapter's httpx.AsyncClient with a mock that returns `response`."""
    mock = AsyncMock()
    mock.post = AsyncMock(return_value=response)
    adapter._client = mock  # type: ignore[attr-defined]
    return mock


# NoOp ----------------------------------------------------------------------


async def test_noop_returns_zero_vector_with_correct_dim() -> None:
    emb = NoOpEmbedding()
    out = await emb.embed(["a", "bb", "ccc"])
    assert len(out) == 3
    for v in out:
        assert len(v) == EMBEDDING_DIM
        assert all(x == 0.0 for x in v)


async def test_noop_empty_input_yields_empty_list() -> None:
    emb = NoOpEmbedding()
    out = await emb.embed([])
    assert out == []


# HTTP ----------------------------------------------------------------------


async def test_http_adapter_calls_embed_endpoint_and_returns_vectors() -> None:
    adapter = HttpEmbeddingAdapter(base_url="http://test.local")
    fake_vector = [0.1] * EMBEDDING_DIM
    resp = _fake_response(
        {"embeddings": [fake_vector, fake_vector], "model": "x", "dim": EMBEDDING_DIM}
    )
    mock = _patch_client(adapter, resp)

    out = await adapter.embed(["one", "two"])

    assert len(out) == 2
    assert out[0] == fake_vector
    # Verify it POSTed to /embed
    args, _ = mock.post.call_args
    assert args[0] == "/embed"
    body = mock.post.call_args.kwargs["json"]
    assert body["input"] == ["one", "two"]
    await adapter.aclose()


async def test_http_adapter_rejects_oversize_batch() -> None:
    adapter = HttpEmbeddingAdapter(base_url="http://test.local", max_batch=2)
    with pytest.raises(ValueError):
        await adapter.embed(["a", "b", "c"])
    await adapter.aclose()


async def test_http_adapter_aclose_is_idempotent() -> None:
    adapter = HttpEmbeddingAdapter(base_url="http://test.local")
    await adapter.aclose()
    await adapter.aclose()  # should not raise


# OpenAI --------------------------------------------------------------------


async def test_openai_adapter_calls_openai_and_preserves_order() -> None:
    adapter = OpenAIEmbeddingAdapter(api_key="sk-test")
    fake = [0.5] * EMBEDDING_DIM
    # OpenAI returns data sorted by index; here we feed them out of order.
    resp = _fake_response(
        {
            "data": [
                {"index": 1, "embedding": fake},
                {"index": 0, "embedding": fake},
            ]
        }
    )
    mock = _patch_client(adapter, resp)

    out = await adapter.embed(["first", "second"])

    assert len(out) == 2
    assert out[0] == fake
    assert out[1] == fake
    args, _ = mock.post.call_args
    assert args[0] == "/embeddings"
    await adapter.aclose()


async def test_openai_adapter_propagates_http_error() -> None:
    adapter = OpenAIEmbeddingAdapter(api_key="sk-test")
    resp = MagicMock()
    resp.raise_for_status = MagicMock(side_effect=RuntimeError("401"))
    resp.json = MagicMock(return_value={"data": []})
    _patch_client(adapter, resp)

    with pytest.raises(RuntimeError, match="401"):
        await adapter.embed(["x"])
    await adapter.aclose()
