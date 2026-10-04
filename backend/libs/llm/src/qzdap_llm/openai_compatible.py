"""OpenAI-compatible client.

Works for any provider exposing `/chat/completions`, `/embeddings` in
OpenAI's shape. We route Anthropic and DeepSeek through here — both
publish OpenAI-compatible endpoints.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx
from qzdap_kernel.errors import ExternalServiceError

from qzdap_llm.client import (
    ChatMessage,
    ChatRequest,
    ChatResponse,
    LLMChunk,
    LLMClient,
    Usage,
)
from qzdap_llm.config import LLMConfig


class OpenAICompatibleClient(LLMClient):
    name = "openai_compatible"

    def __init__(
        self, config: LLMConfig, *, http: httpx.AsyncClient | None = None
    ) -> None:
        self._cfg = config
        self._http = http or httpx.AsyncClient(
            base_url=config.base_url,
            timeout=config.timeout_seconds,
            headers={"Authorization": f"Bearer {config.api_key}"}
            if config.api_key
            else {},
        )

    async def chat(self, req: ChatRequest) -> ChatResponse:
        payload = _build_payload(req, stream=False)
        try:
            resp = await self._http.post("/chat/completions", json=payload)
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPError as e:
            raise ExternalServiceError(
                f"LLM chat failed: {e}", code="LLM_UPSTREAM_ERROR"
            ) from e
        return _parse_chat_response(data)

    async def stream(self, req: ChatRequest) -> AsyncIterator[LLMChunk]:
        payload = _build_payload(req, stream=True)
        try:
            async with self._http.stream(
                "POST", "/chat/completions", json=payload
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    body = line[len("data: ") :]
                    if body == "[DONE]":
                        return
                    try:
                        data = json.loads(body)
                    except json.JSONDecodeError:
                        continue
                    chunk = _parse_stream_chunk(data)
                    if chunk is not None:
                        yield chunk
        except httpx.HTTPError as e:
            raise ExternalServiceError(
                f"LLM stream failed: {e}", code="LLM_UPSTREAM_ERROR"
            ) from e

    async def embed(self, texts: list[str]) -> list[list[float]]:
        try:
            resp = await self._http.post(
                "/embeddings",
                json={"input": texts, "model": self._cfg.embedding_model},
            )
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPError as e:
            raise ExternalServiceError(
                f"LLM embed failed: {e}", code="LLM_UPSTREAM_ERROR"
            ) from e
        return [item["embedding"] for item in data["data"]]

    async def aclose(self) -> None:
        await self._http.aclose()


def _build_payload(req: ChatRequest, *, stream: bool) -> dict:
    out: dict = {
        "model": req.model,
        "messages": [
            {
                "role": m.role,
                "content": m.content,
                **({"name": m.name} if m.name else {}),
                **({"tool_call_id": m.tool_call_id} if m.tool_call_id else {}),
                **({"tool_calls": m.tool_calls} if m.tool_calls else {}),
            }
            for m in req.messages
        ],
        "temperature": req.temperature,
        "stream": stream,
    }
    if req.max_tokens is not None:
        out["max_tokens"] = req.max_tokens
    if req.top_p is not None:
        out["top_p"] = req.top_p
    if req.stop:
        out["stop"] = req.stop
    if req.tools:
        out["tools"] = req.tools
    if req.tool_choice is not None:
        out["tool_choice"] = req.tool_choice
    if req.response_format:
        out["response_format"] = req.response_format
    return out


def _parse_chat_response(data: dict) -> ChatResponse:
    choice = data["choices"][0]
    msg = choice["message"]
    usage_data = data.get("usage") or {}
    return ChatResponse(
        model=data["model"],
        message=ChatMessage(
            role=msg["role"],
            content=msg.get("content") or "",
            tool_calls=msg.get("tool_calls"),
        ),
        finish_reason=choice.get("finish_reason") or "stop",
        usage=Usage(
            input_tokens=usage_data.get("prompt_tokens", 0),
            output_tokens=usage_data.get("completion_tokens", 0),
            cache_read_tokens=usage_data.get("cache_read_input_tokens", 0),
            cache_write_tokens=usage_data.get("cache_creation_input_tokens", 0),
        ),
        raw=data,
    )


def _parse_stream_chunk(data: dict) -> LLMChunk | None:
    if not data.get("choices"):
        return None
    choice = data["choices"][0]
    delta = choice.get("delta") or {}
    return LLMChunk(
        model=data.get("model", ""),
        delta=delta.get("content") or "",
        finish_reason=choice.get("finish_reason"),
        tool_calls=delta.get("tool_calls"),
    )
