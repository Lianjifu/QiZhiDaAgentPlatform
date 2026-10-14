from __future__ import annotations

import asyncio

import httpx
import pytest

from qzdap.modules.model.adapter.llm.connectivity_tester import (
    HttpConnectivityTester,
    PublicNetworkTransport,
    UnsafeDestinationError,
)


async def _public_dns(*_args, **_kwargs):
    return [(None, None, None, None, ("93.184.216.34", 443))]


@pytest.mark.asyncio
async def test_openai_connectivity_sends_real_chat_request(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["auth"] = request.headers["authorization"]
        captured["body"] = request.read()
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-test",
                "model": "gpt-test",
                "choices": [
                    {
                        "message": {"role": "assistant", "content": "OK"},
                        "finish_reason": "stop",
                    }
                ],
            },
        )

    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", _public_dns)
    result = await HttpConnectivityTester(
        transport=httpx.MockTransport(handler)
    ).test_connection(
        api_key="sk-test",
        base_url="https://example.com/v1",
        protocol="openai",
        model="gpt-test",
        api_version="",
    )

    assert result["success"] is True
    assert captured["path"] == "/v1/chat/completions"
    assert captured["auth"] == "Bearer sk-test"


@pytest.mark.asyncio
async def test_anthropic_connectivity_uses_messages_wire_format(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["key"] = request.headers["x-api-key"]
        return httpx.Response(
            200,
            json={
                "id": "msg_test",
                "type": "message",
                "role": "assistant",
                "model": "claude-test",
                "content": [{"type": "text", "text": "OK"}],
                "stop_reason": "end_turn",
            },
        )

    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", _public_dns)
    result = await HttpConnectivityTester(
        transport=httpx.MockTransport(handler)
    ).test_connection(
        api_key="sk-ant-test",
        base_url="https://example.com/anthropic",
        protocol="anthropic",
        model="claude-test",
        api_version="",
    )

    assert result["success"] is True
    assert captured["path"] == "/anthropic/v1/messages"
    assert captured["key"] == "sk-ant-test"


@pytest.mark.asyncio
async def test_connectivity_redacts_upstream_failure(monkeypatch) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "sk-secret invalid"}})

    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", _public_dns)
    result = await HttpConnectivityTester(
        transport=httpx.MockTransport(handler)
    ).test_connection(
        api_key="sk-secret",
        base_url="https://example.com/v1",
        protocol="openai",
        model="gpt-test",
        api_version="",
    )

    assert result["success"] is False
    assert result["statusCode"] == 401
    assert "sk-secret" not in str(result)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "ip", ["127.0.0.1", "10.0.0.1", "169.254.169.254", "::1", "::ffff:127.0.0.1"]
)
async def test_public_transport_blocks_non_public_destinations(monkeypatch, ip) -> None:
    async def dns(*_args, **_kwargs):
        return [(None, None, None, None, (ip, 443))]

    def handler(_request):
        pytest.fail("Private destination reached transport")

    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", dns)
    transport = PublicNetworkTransport(httpx.MockTransport(handler))
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(UnsafeDestinationError):
            await client.get("https://attacker.example/models")


@pytest.mark.asyncio
async def test_public_transport_pins_ip_retains_host_and_tls_identity(
    monkeypatch,
) -> None:
    seen = []

    def handler(request):
        seen.append(
            (
                request.url.host,
                request.headers["host"],
                request.extensions["sni_hostname"],
            )
        )
        return httpx.Response(200, json={})

    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", _public_dns)
    async with httpx.AsyncClient(
        transport=PublicNetworkTransport(httpx.MockTransport(handler))
    ) as client:
        await client.get("https://provider.example/models")
    assert seen == [("93.184.216.34", "provider.example", "provider.example")]


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [301, 302, 307, 400, 401, 404, 429, 500])
async def test_connectivity_never_retries_or_follows_redirect(
    monkeypatch, status
) -> None:
    visited = []

    def handler(request):
        visited.append(request.url.path)
        return httpx.Response(
            status,
            headers={"location": "http://127.0.0.1/"},
            json={"error": "sk-secret"},
        )

    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", _public_dns)
    result = await HttpConnectivityTester(
        transport=httpx.MockTransport(handler)
    ).test_connection(
        api_key="sk-secret",
        base_url="https://provider.example/v1",
        protocol="openai",
        model="test",
        api_version="",
    )
    assert result["success"] is False
    assert result["statusCode"] == status
    assert "sk-secret" not in str(result)
    assert len(visited) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body",
    [
        "invalid",
        "{}",
        '{"choices":[]}',
        '{"choices":[{"message":{"role":"assistant","content":" "}}]}',
    ],
)
async def test_http_200_without_valid_generated_text_is_failure(
    monkeypatch, body
) -> None:
    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", _public_dns)
    result = await HttpConnectivityTester(
        transport=httpx.MockTransport(lambda _req: httpx.Response(200, text=body))
    ).test_connection(
        api_key="key",
        base_url="https://provider.example/v1",
        protocol="openai",
        model="test",
        api_version="",
    )
    assert result["success"] is False
    assert result["statusCode"] == 200


@pytest.mark.asyncio
async def test_connectivity_limits_body_and_redacts_key_echo(monkeypatch) -> None:
    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", _public_dns)
    for value, expected_success in [("OK sk-secret", True), ("a" * 70_000, False)]:
        result = await HttpConnectivityTester(
            transport=httpx.MockTransport(
                lambda _req, value=value: httpx.Response(
                    200,
                    json={
                        "model": "model",
                        "choices": [
                            {"message": {"role": "assistant", "content": value}}
                        ],
                    },
                )
            )
        ).test_connection(
            api_key="sk-secret",
            base_url="https://provider.example/v1",
            protocol="openai",
            model="test",
            api_version="",
        )
        assert result["success"] is expected_success
        assert "sk-secret" not in str(result)


@pytest.mark.asyncio
async def test_connectivity_total_deadline_includes_dns(monkeypatch) -> None:
    async def dns(*_args, **_kwargs):
        await asyncio.sleep(0.05)
        return await _public_dns()

    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", dns)
    result = await HttpConnectivityTester(
        timeout_seconds=0.005,
        transport=httpx.MockTransport(lambda _req: httpx.Response(200)),
    ).test_connection(
        api_key="key",
        base_url="https://provider.example/v1",
        protocol="openai",
        model="test",
        api_version="",
    )
    assert result["success"] is False
    assert result["statusCode"] is None
    assert "超时" in result["error"]
