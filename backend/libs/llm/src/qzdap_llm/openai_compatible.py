"""OpenAI Chat Completions transport, including branded compatible APIs."""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx

from qzdap_llm.client import (
    ChatMessage,
    ChatRequest,
    ChatResponse,
    LLMChunk,
    Usage,
)
from qzdap_llm.config import LLMConfig
from qzdap_llm.transport import HTTPProviderClient, ProviderTransportError


class OpenAICompatibleClient(HTTPProviderClient):
    name = "openai_compatible"

    def __init__(
        self, config: LLMConfig, *, http: httpx.AsyncClient | None = None
    ) -> None:
        self._cfg = config
        super().__init__(
            base_url=config.base_url,
            headers={"Authorization": f"Bearer {config.api_key}"}
            if config.api_key
            else {},
            timeout_seconds=config.timeout_seconds,
            http=http,
        )

    def _chat_path(self, model: str) -> str:
        return "chat/completions"

    async def chat(self, req: ChatRequest) -> ChatResponse:
        data = await self._post(
            self._chat_path(req.model), _build_payload(req, stream=False)
        )
        try:
            return _parse_chat_response(data)
        except (KeyError, IndexError, TypeError, ValueError, AttributeError):
            raise ProviderTransportError(code="LLM_INVALID_RESPONSE") from None

    async def stream(self, req: ChatRequest) -> AsyncIterator[LLMChunk]:
        events = self._events(
            self._chat_path(req.model), _build_payload(req, stream=True)
        )
        try:
            async for _, data in events:
                try:
                    chunk = _parse_stream_chunk(data)
                except (KeyError, IndexError, TypeError, ValueError, AttributeError):
                    raise ProviderTransportError(code="LLM_INVALID_RESPONSE") from None
                if chunk is not None:
                    yield chunk
        finally:
            await events.aclose()

    async def embed(self, texts: list[str]) -> list[list[float]]:
        data = await self._post(
            "embeddings", {"input": texts, "model": self._cfg.embedding_model}
        )
        try:
            return [item["embedding"] for item in data["data"]]
        except (KeyError, TypeError):
            raise ProviderTransportError(code="LLM_INVALID_RESPONSE") from None


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
    if stream:
        out["stream_options"] = {"include_usage": True}
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
        usage=_parse_usage(usage_data),
        raw=data,
    )


def _parse_usage(data: dict) -> Usage:
    return Usage(
        input_tokens=data.get("prompt_tokens", 0),
        output_tokens=data.get("completion_tokens", 0),
        cache_read_tokens=(data.get("prompt_tokens_details") or {}).get(
            "cached_tokens", data.get("cache_read_input_tokens", 0)
        ),
        cache_write_tokens=data.get("cache_creation_input_tokens", 0),
    )


def _parse_stream_chunk(data: dict) -> LLMChunk | None:
    usage = _parse_usage(data["usage"]) if data.get("usage") is not None else None
    if not data.get("choices"):
        return (
            LLMChunk(model=data.get("model", ""), delta="", usage=usage)
            if usage
            else None
        )
    choice = data["choices"][0]
    delta = choice.get("delta") or {}
    return LLMChunk(
        model=data.get("model", ""),
        delta=delta.get("content") or "",
        finish_reason=choice.get("finish_reason"),
        tool_calls=delta.get("tool_calls"),
        usage=usage,
    )
