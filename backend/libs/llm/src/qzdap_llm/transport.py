"""HTTP ownership, sanitized failures and provider-neutral SSE framing."""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator, AsyncIterator

import httpx
from qzdap_kernel.errors import ExternalServiceError

from qzdap_llm.client import LLMClient


class ProviderTransportError(ExternalServiceError):
    """Safe upstream failure; status_code is diagnostic data, not envelope status."""

    def __init__(
        self, *, status_code: int | None = None, code: str = "LLM_UPSTREAM_ERROR"
    ):
        super().__init__("LLM provider request failed", code=code)
        self.status_code = status_code


def transport_error(exc: httpx.HTTPError) -> ProviderTransportError:
    status = (
        exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
    )
    return ProviderTransportError(status_code=status)


def decode_object(body: str) -> dict:
    try:
        value = json.loads(body)
        if not isinstance(value, dict):
            raise TypeError
        return value
    except (ValueError, TypeError):
        raise ProviderTransportError(code="LLM_INVALID_RESPONSE") from None


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
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._headers = headers
        self._timeout = timeout_seconds
        self._owns_http = http is None
        self._http = (
            http if http is not None else httpx.AsyncClient(timeout=timeout_seconds)
        )

    def _url(self, path: str) -> str:
        return f"{self._base_url}/{path.lstrip('/')}"

    async def _post(self, path: str, payload: dict) -> dict:
        try:
            response = await self._http.post(
                self._url(path),
                json=payload,
                headers=self._headers,
                timeout=self._timeout,
            )
            response.raise_for_status()
            return decode_object(response.text)
        except httpx.HTTPError as exc:
            raise transport_error(exc) from None

    async def _events(
        self, path: str, payload: dict
    ) -> AsyncGenerator[tuple[str, dict]]:
        try:
            async with self._http.stream(
                "POST",
                self._url(path),
                json=payload,
                headers=self._headers,
                timeout=self._timeout,
            ) as response:
                response.raise_for_status()
                received = False
                async for event, body in iter_sse(response):
                    received = True
                    if body == "[DONE]":
                        return
                    data = decode_object(body)
                    if event == "error" or "error" in data:
                        raise ProviderTransportError(code="LLM_STREAM_ERROR")
                    yield event, data
                if not received:
                    raise ProviderTransportError(code="LLM_INVALID_RESPONSE")
        except httpx.HTTPError as exc:
            raise transport_error(exc) from None

    async def aclose(self) -> None:
        if self._owns_http:
            await self._http.aclose()
