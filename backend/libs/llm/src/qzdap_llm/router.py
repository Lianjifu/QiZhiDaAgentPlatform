"""Multi-provider LLM router with failover."""

from __future__ import annotations

from collections.abc import AsyncIterator

from qzdap_kernel.errors import ExternalServiceError

from qzdap_llm.client import ChatRequest, ChatResponse, LLMChunk, LLMClient


class LLMRouter(LLMClient):
    """Routes to primary client; on failure, tries failover clients in order."""

    name = "router"

    def __init__(
        self, primary: LLMClient, failovers: list[LLMClient] | None = None
    ) -> None:
        self._primary = primary
        self._failovers = list(failovers or [])
        self._chain: list[LLMClient] = [primary, *self._failovers]

    async def chat(self, req: ChatRequest) -> ChatResponse:
        resp = await self._with_failover(lambda c: c.chat(req))
        return resp  # type: ignore[return-value]

    async def stream(self, req: ChatRequest) -> AsyncIterator[LLMChunk]:  # type: ignore[override]
        # For streaming, fail-over is per-first-chunk; we re-issue on first
        # chunk failure. Mid-stream errors terminate the stream.
        last_exc: Exception | None = None
        for client in self._chain:
            try:
                stream = client.stream(req)
                async for chunk in stream:
                    yield chunk
                return
            except ExternalServiceError as e:
                last_exc = e
                continue
        raise last_exc or ExternalServiceError(
            "no provider succeeded", code="LLM_ALL_FAILED"
        )

    async def embed(self, texts: list[str]) -> list[list[float]]:
        resp = await self._with_failover(lambda c: c.embed(texts))
        return resp  # type: ignore[return-value]

    async def _with_failover(self, fn: object) -> object:
        last_exc: Exception | None = None
        for client in self._chain:
            try:
                return await fn(client)  # type: ignore[operator]
            except ExternalServiceError as e:
                last_exc = e
                continue
        raise last_exc or ExternalServiceError(
            "no provider succeeded", code="LLM_ALL_FAILED"
        )
