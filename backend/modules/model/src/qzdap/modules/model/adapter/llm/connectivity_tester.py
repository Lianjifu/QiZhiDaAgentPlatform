"""Verify provider credentials using the same adapters as saved invocation."""

from __future__ import annotations

import asyncio
import ipaddress
import socket
import time
from collections.abc import AsyncIterator
from urllib.parse import parse_qsl, urlsplit

import httpx
from qzdap_llm import ChatMessage, ChatRequest
from qzdap_llm.providers import build_provider_client, get_provider_spec

from qzdap.modules.model.application.ports import ConnectivityTester

_MAX_RESPONSE_BYTES = 65_536


class UnsafeDestinationError(ValueError):
    pass


class ResponseTooLargeError(ValueError):
    pass


class _BoundedStream(httpx.AsyncByteStream):
    def __init__(self, stream: httpx.AsyncByteStream) -> None:
        self._stream = stream

    async def __aiter__(self) -> AsyncIterator[bytes]:
        count = 0
        async for chunk in self._stream:
            count += len(chunk)
            if count > _MAX_RESPONSE_BYTES:
                raise ResponseTooLargeError
            yield chunk

    async def aclose(self) -> None:
        await self._stream.aclose()


class PublicNetworkTransport(httpx.AsyncBaseTransport):
    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport or httpx.AsyncHTTPTransport(
            retries=0, trust_env=False
        )
        self.status_code: int | None = None

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        host = request.url.host
        addresses = await asyncio.get_running_loop().getaddrinfo(
            host,
            request.url.port or (443 if request.url.scheme == "https" else 80),
            type=socket.SOCK_STREAM,
        )
        ips = [ipaddress.ip_address(item[4][0]) for item in addresses]
        if not ips or any(not ip.is_global for ip in ips):
            raise UnsafeDestinationError
        # Pin the validated address, retaining the original Host and TLS identity.
        pinned = httpx.Request(
            request.method,
            request.url.copy_with(host=str(ips[0])),
            headers=request.headers,
            stream=request.stream,
            extensions={**request.extensions, "sni_hostname": host},
        )
        response = await self._transport.handle_async_request(pinned)
        self.status_code = response.status_code
        if response.is_stream_consumed and len(response.content) > _MAX_RESPONSE_BYTES:
            raise ResponseTooLargeError
        response.stream = _BoundedStream(response.stream)
        return response

    async def aclose(self) -> None:
        await self._transport.aclose()


def validate_provider_url(base_url: str, protocol: str) -> None:
    parts = urlsplit(base_url.strip())
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        raise ValueError("invalid URL")
    if parts.username is not None or parts.password is not None or parts.fragment:
        raise ValueError("invalid URL")
    _ = parts.port
    query = parse_qsl(parts.query, keep_blank_values=True)
    if query and (
        protocol != "azure" or len(query) != 1 or query[0][0] != "api-version"
    ):
        raise ValueError("invalid query")


class HttpConnectivityTester(ConnectivityTester):
    def __init__(
        self,
        *,
        timeout_seconds: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._timeout = timeout_seconds
        self._transport = transport

    async def test_connection(
        self,
        *,
        api_key: str,
        base_url: str,
        protocol: str,
        model: str,
        api_version: str,
    ) -> dict[str, object]:
        started = time.perf_counter()
        result: dict[str, object] = {
            "success": False,
            "latencyMs": 0,
            "statusCode": None,
            "requestedModel": _redact(model, api_key, 256),
            "actualModel": None,
            "response": None,
            "error": None,
        }
        transport = PublicNetworkTransport(self._transport)
        try:
            async with asyncio.timeout(self._timeout):
                spec = get_provider_spec(protocol)
                resolved_url = base_url.strip() or spec.default_base_url
                validate_provider_url(resolved_url, protocol)
                if not api_key or not model.strip() or len(model) > 256:
                    raise ValueError("missing credentials or model")
                async with httpx.AsyncClient(
                    timeout=self._timeout,
                    follow_redirects=False,
                    trust_env=False,
                    transport=transport,
                ) as http:
                    client = build_provider_client(
                        protocol=protocol,
                        api_key=api_key,
                        base_url=resolved_url,
                        api_version=api_version,
                        timeout_seconds=self._timeout,
                        http=http,
                    )
                    try:
                        response = await client.chat(
                            ChatRequest(
                                model=model.strip(),
                                max_tokens=32,
                                messages=[
                                    ChatMessage(role="user", content="Reply with OK.")
                                ],
                            )
                        )
                    finally:
                        await client.aclose()
                text = response.message.content
                if not isinstance(text, str) or not text.strip():
                    result["error"] = "供应商返回成功状态，但没有有效的生成文本。"
                    return result
                raw = response.raw or {}
                actual = (
                    raw.get("modelVersion")
                    if spec.transport == "google"
                    else raw.get("model")
                )
                result.update(
                    success=True,
                    actualModel=_redact(actual, api_key, 256)
                    if isinstance(actual, str)
                    else None,
                    response=_redact(text.strip(), api_key, 500),
                )
        except (TimeoutError, httpx.TimeoutException):
            result["error"] = "供应商请求超时。"
        except UnsafeDestinationError:
            result["error"] = "请求地址必须指向公网，不能访问内网或本机。"
        except ResponseTooLargeError:
            result["error"] = "供应商响应超过诊断大小限制。"
        except ValueError:
            result["error"] = "配置或响应无效，请检查协议、地址、模型 ID 和 API 版本。"
        except Exception:  # noqa: BLE001 — upstream exceptions may contain credentials
            status = transport.status_code
            result["error"] = (
                f"供应商返回 HTTP {status}。"
                if status and not 200 <= status < 300
                else "供应商调用失败，请检查配置、网络及响应格式。"
            )
        finally:
            result["statusCode"] = transport.status_code
            result["latencyMs"] = max(0, int((time.perf_counter() - started) * 1000))
            await transport.aclose()
        return result


def _redact(value: str, api_key: str, limit: int) -> str:
    return value.replace(api_key, "[REDACTED]")[:limit] if api_key else value[:limit]


__all__ = ["HttpConnectivityTester", "PublicNetworkTransport", "validate_provider_url"]
