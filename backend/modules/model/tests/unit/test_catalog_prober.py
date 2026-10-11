"""Unit tests for HttpCatalogProber."""

from __future__ import annotations

import httpx
import pytest

from qzdap.modules.model.adapter.llm.prober import ANTHROPIC_VERSION, HttpCatalogProber


def _async_client_with(handler, real_async_client):
    transport = httpx.MockTransport(handler)
    return real_async_client(transport=transport, timeout=5.0)


@pytest.mark.asyncio
async def test_openai_compatible_parses_data_array(monkeypatch) -> None:
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("authorization", "")
        return httpx.Response(200, json={"data": [{"id": "gpt-4o"}, {"id": "gpt-4o-mini"}]})

    real_async_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda *args, **kwargs: _async_client_with(handler, real_async_client),
    )
    prober = HttpCatalogProber(timeout_seconds=2.0)
    names = await prober.list_models(
        api_key="sk-test", base_url="https://example.com/v1", protocol="openai"
    )
    assert names == ["gpt-4o", "gpt-4o-mini"]
    assert captured["url"] == "https://example.com/v1/models"
    assert captured["auth"] == "Bearer sk-test"


@pytest.mark.asyncio
async def test_anthropic_uses_x_api_key_and_v1_models(monkeypatch) -> None:
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["x-api-key"] = request.headers.get("x-api-key", "")
        captured["anthropic-version"] = request.headers.get("anthropic-version", "")
        return httpx.Response(
            200,
            json={
                "data": [
                    {"id": "claude-3-5-sonnet-20241022", "display_name": "Claude 3.5 Sonnet"},
                    {"id": "claude-3-5-haiku-20241022", "display_name": "Claude 3.5 Haiku"},
                ],
                "has_more": False,
            },
        )

    real_async_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda *args, **kwargs: _async_client_with(handler, real_async_client),
    )
    prober = HttpCatalogProber(timeout_seconds=2.0)
    names = await prober.list_models(
        api_key="sk-ant-test",
        base_url="https://api.anthropic.com",
        protocol="anthropic",
    )
    assert names == ["claude-3-5-sonnet-20241022", "claude-3-5-haiku-20241022"]
    assert captured["url"] == "https://api.anthropic.com/v1/models"
    assert captured["x-api-key"] == "sk-ant-test"
    assert captured["anthropic-version"] == ANTHROPIC_VERSION


@pytest.mark.asyncio
async def test_openai_compatible_propagates_status_error(monkeypatch) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "invalid api key"})

    real_async_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda *args, **kwargs: _async_client_with(handler, real_async_client),
    )
    prober = HttpCatalogProber(timeout_seconds=2.0)
    with pytest.raises(httpx.HTTPStatusError):
        await prober.list_models(
            api_key="sk-bad", base_url="https://example.com/v1", protocol="openai"
        )


@pytest.mark.asyncio
async def test_anthropic_compatible_uses_anthropic_headers(monkeypatch) -> None:
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["x-api-key"] = request.headers.get("x-api-key", "")
        captured["auth"] = request.headers.get("authorization", "")
        return httpx.Response(
            200,
            json={"data": [{"id": "claude-3-5-sonnet-proxy"}], "has_more": False},
        )

    real_async_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda *args, **kwargs: _async_client_with(handler, real_async_client),
    )
    prober = HttpCatalogProber(timeout_seconds=2.0)
    names = await prober.list_models(
        api_key="sk-third-party",
        base_url="https://thirdparty.example.com",
        protocol="anthropic-compatible",
    )
    assert names == ["claude-3-5-sonnet-proxy"]
    assert captured["url"] == "https://thirdparty.example.com/v1/models"
    assert captured["x-api-key"] == "sk-third-party"
    # Bearer should NOT be set — Anthropic uses x-api-key only.
    assert captured["auth"] == ""


@pytest.mark.asyncio
async def test_extract_ids_handles_plain_strings(monkeypatch) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=["gpt-4o", "gpt-4o-mini"])

    real_async_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda *args, **kwargs: _async_client_with(handler, real_async_client),
    )
    prober = HttpCatalogProber(timeout_seconds=2.0)
    names = await prober.list_models(
        api_key="sk-test", base_url="https://example.com/v1", protocol="openai-compatible"
    )
    assert names == ["gpt-4o", "gpt-4o-mini"]