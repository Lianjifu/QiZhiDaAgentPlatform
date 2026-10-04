"""Tests for the embedding runtime sidecar (skeleton + openai + noop)."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from qzdap.runtimes.embedding_runtime.adapters.noop_adapter import NoOpAdapter
from qzdap.runtimes.embedding_runtime.app import create_app
from qzdap.runtimes.embedding_runtime.routes import build_router

# NoOp ----------------------------------------------------------------------


def test_noop_app_embeds_and_reports_health() -> None:
    app = create_app(provider="noop")
    client = TestClient(app)

    h = client.get("/healthz")
    assert h.status_code == 200
    body = h.json()
    assert body["status"] == "ok"
    assert body["provider"] == "noop"

    r = client.post("/embed", json={"input": ["alpha", "bravo"]})
    assert r.status_code == 200
    body = r.json()
    assert body["model"] == "noop"
    assert body["dim"] == 1536
    assert len(body["embeddings"]) == 2
    assert all(len(v) == 1536 for v in body["embeddings"])


def test_noop_rejects_empty_input() -> None:
    app = create_app(provider="noop")
    client = TestClient(app)
    r = client.post("/embed", json={"input": []})
    assert r.status_code == 422


def test_noop_rejects_oversize_batch() -> None:
    app = create_app(provider="noop")
    client = TestClient(app)
    r = client.post("/embed", json={"input": ["x"] * 200})
    assert r.status_code == 422


# OpenAI --------------------------------------------------------------------


def test_openai_app_embeds_via_mock_client() -> None:
    app = create_app(provider="openai", openai_api_key="sk-test")
    # patch the openai adapter's client
    adapter = app.state.embedding_adapter
    fake_vector = [0.1] * 1536
    resp = MagicMock()
    resp.json = MagicMock(
        return_value={"data": [{"index": 0, "embedding": fake_vector}]}
    )
    resp.raise_for_status = MagicMock()
    mock = AsyncMock()
    mock.post = AsyncMock(return_value=resp)
    adapter._client = mock

    client = TestClient(app)
    r = client.post("/embed", json={"input": ["hello"]})
    assert r.status_code == 200
    body = r.json()
    assert body["model"] == "text-embedding-3-small"
    assert body["dim"] == 1536
    assert body["embeddings"][0] == fake_vector
    args, _ = mock.post.call_args
    assert args[0] == "/embeddings"


def test_openai_without_key_raises_at_startup() -> None:
    # Reset module-level Settings cache + os.environ for this test
    from qzdap.runtimes.embedding_runtime.settings import reset_settings_cache

    os.environ.pop("QZDAP_OPENAI_API_KEY", None)
    reset_settings_cache()
    with pytest.raises(RuntimeError, match="QZDAP_OPENAI_API_KEY required"):
        create_app(provider="openai")


def test_unknown_provider_raises() -> None:
    with pytest.raises(RuntimeError, match="unknown QZDAP_EMBEDDING_PROVIDER"):
        create_app(provider="bogus")


# Build_router shape --------------------------------------------------------


def test_build_router_returns_router_instance() -> None:
    from fastapi import APIRouter

    r = build_router()
    assert isinstance(r, APIRouter)
    # /embed and /healthz present
    paths: set[str] = set()
    for route in r.routes:
        path = getattr(route, "path", None)
        if path is not None:
            paths.add(path)
    assert "/embed" in paths
    assert "/healthz" in paths


def test_router_500_when_adapter_missing() -> None:
    """Without the adapter wired, the dependency raises RuntimeError which
    bubbles up as a 500 — the runtime never silently serves wrong data.
    """
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(build_router())  # no adapter wired
    # raise_server_exceptions=False makes the test client return the
    # response shape instead of re-raising the underlying RuntimeError.
    client = TestClient(app, raise_server_exceptions=False)
    r = client.post("/embed", json={"input": ["x"]})
    assert r.status_code == 500
    h = client.get("/healthz")
    assert h.status_code == 500


# silence unused-import lint guard
_ = NoOpAdapter
