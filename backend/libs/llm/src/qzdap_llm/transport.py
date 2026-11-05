"""HTTP ownership, sanitized failures and provider-neutral SSE framing."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncGenerator, AsyncIterator, Awaitable, Callable

import httpx

from qzdap_kernel.error_codes import ErrorCode
from qzdap_kernel.errors import ExternalServiceError
from qzdap_llm.client import LLMClient
from qzdap_llm.retry import RetryPolicy, retry_after_seconds

_log = logging.getLogger(__name__)


class ProviderTransportError(ExternalServiceError):
    """Safe upstream failure; status_code is diagnostic data, not envelope status."""

    def __init__(self, *, status_code: int | None = None, code: str = "LLM_UPSTREAM_ERROR"):
        super().__init__("LLM provider request failed", code=code)
        self.status_code = status_code


def transport_error(exc: httpx.HTTPError) -> ProviderTransportError:
    status = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
    return ProviderTransportError(status_code=status)


def decode_object(body: str) -> dict:
    try:
        value = json.loads(body)
        if not isinstance(value, dict):
            raise TypeError
        return value
    except (ValueError, TypeError):
        raise ProviderTransportError(code=ErrorCode.LLM_INVALID_RESPONSE.value) from None


async def iter_sse(resp: httpx.Response) -> AsyncIterator[tuple[str, str]]:
    """Read SSE events (multiline data, comments, CRLF and EOF included)."""
    event = "message"
    lines: list[str] = []
    async for line in resp.aiter_lines():
        if not line:
            if lines:
                yield event, "\n".join(lines)
            event, lines = "message", []
        elif line.startswith("event:"):
            event = line[6:].lstrip(" ")
        elif line.startswith("data:"):
            lines.append(line[5:].removeprefix(" "))
    if lines:
        yield event, "\n".join(lines)


class HTTPProviderClient(LLMClient):
    def __init__(
        self,
        *,
        base_url: str,
        headers: dict[str, str],
        timeout_seconds: float,
        http: httpx.AsyncClient | None = None,
        retry_policy: RetryPolicy | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._headers = headers
        self._timeout = timeout_seconds
        self._owns_http = http is None
        self._http = http if http is not None else httpx.AsyncClient(timeout=timeout_seconds)
        self._retry = retry_policy or RetryPolicy()
        # ⚠️ **可替换的 sleep** ✓ —— 测试里要能断言退避时长 ✓（真等会拖慢套件 ✗✗）。
        self._sleep: Callable[[float], Awaitable[None]] = asyncio.sleep

    def _url(self, path: str) -> str:
        return f"{self._base_url}/{path.lstrip('/')}"

    async def _wait_before_retry(self, attempt: int, headers: httpx.Headers | None) -> None:
        """**重试前等一下** ✓ —— 指数退避 ✓ + jitter ✓，``Retry-After`` 优先 ✓。"""
        hinted = retry_after_seconds(headers)
        delay = hinted if hinted is not None else self._retry.delay_seconds(attempt)
        if delay > 0:
            await self._sleep(delay)

    async def _post(self, path: str, payload: dict) -> dict:
        attempts = self._retry.max_attempts
        for attempt in range(1, attempts + 1):
            try:
                response = await self._http.post(
                    self._url(path),
                    json=payload,
                    headers=self._headers,
                    timeout=self._timeout,
                )
            except httpx.HTTPError as exc:
                if attempt < attempts and self._retry.should_retry_exception(exc):
                    _log.warning(
                        "llm transport error, retrying (%d/%d): %s", attempt, attempts, exc
                    )
                    await self._wait_before_retry(attempt, None)
                    continue
                raise transport_error(exc) from None
            if response.status_code >= 400:
                if attempt < attempts and self._retry.should_retry_status(response.status_code):
                    _log.warning(
                        "llm upstream status %d, retrying (%d/%d)",
                        response.status_code,
                        attempt,
                        attempts,
                    )
                    await self._wait_before_retry(attempt, response.headers)
                    continue
                raise ProviderTransportError(status_code=response.status_code) from None
            return decode_object(response.text)
        raise ProviderTransportError()  # pragma: no cover — 循环必然返回或抛出

    async def _events(self, path: str, payload: dict) -> AsyncGenerator[tuple[str, dict]]:
        attempts = self._retry.max_attempts
        for attempt in range(1, attempts + 1):
            # ⚠️ **已经吐过 chunk 就不重试了** ✓ —— 重放会**重复吐字** ✗✗。
            emitted = False
            retry_status: int | None = None
            retry_headers: httpx.Headers | None = None
            try:
                async with self._http.stream(
                    "POST",
                    self._url(path),
                    json=payload,
                    headers=self._headers,
                    timeout=self._timeout,
                ) as response:
                    if response.status_code >= 400:
                        retry_status = response.status_code
                        retry_headers = response.headers
                    else:
                        response.raise_for_status()
                        received = False
                        async for event, body in iter_sse(response):
                            received = True
                            if body == "[DONE]":
                                return
                            data = decode_object(body)
                            if event == "error" or "error" in data:
                                raise ProviderTransportError(code=ErrorCode.LLM_STREAM_ERROR.value)
                            emitted = True
                            yield event, data
                        if not received:
                            raise ProviderTransportError(code=ErrorCode.LLM_INVALID_RESPONSE.value)
            except httpx.HTTPError as exc:
                if emitted:
                    # ⚠️ **流已经开始** ✓ —— 只能中断 ✗✗（重放会重复吐字 ✗✗）。
                    raise transport_error(exc) from None
                if attempt < attempts and self._retry.should_retry_exception(exc):
                    _log.warning(
                        "llm stream transport error, retrying (%d/%d): %s", attempt, attempts, exc
                    )
                    await self._wait_before_retry(attempt, None)
                    continue
                raise transport_error(exc) from None
            if retry_status is not None:
                if attempt < attempts and self._retry.should_retry_status(retry_status):
                    _log.warning(
                        "llm stream status %d, retrying (%d/%d)",
                        retry_status,
                        attempt,
                        attempts,
                    )
                    await self._wait_before_retry(attempt, retry_headers)
                    continue
                raise ProviderTransportError(status_code=retry_status) from None
            return
        raise ProviderTransportError()  # pragma: no cover — 循环必然返回或抛出

    async def aclose(self) -> None:
        if self._owns_http:
            await self._http.aclose()
