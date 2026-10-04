"""Drain LLMPort streams into assistant text + tool_calls."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Awaitable
from typing import Any
from uuid import uuid4

from qzdap_llm.client import ChatMessage, ChatRequest
from qzdap_schema.ids import ModelId

from qzdap.modules.agent_runtime.application.ports import LLMPort

DeltaCallback = Callable[[str], Awaitable[None]]


async def complete_chat(
    llm: LLMPort,
    *,
    model: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    model_id: ModelId | None = None,
    on_delta: DeltaCallback | None = None,
) -> dict[str, Any]:
    req = ChatRequest(
        model=model,
        messages=[
            ChatMessage(
                role=item.get("role") or "user",  # type: ignore[arg-type]
                content=str(item.get("content") or ""),
                name=item.get("name"),
                tool_call_id=item.get("tool_call_id"),
                tool_calls=item.get("tool_calls"),
            )
            for item in messages
        ],
        tools=tools or None,
    )
    text_parts: list[str] = []
    tool_calls: list[dict[str, Any]] = []
    usage: dict[str, int] = {"input_tokens": 0, "output_tokens": 0}
    stream: AsyncIterator = llm.stream(req, model_id=model_id)
    async for chunk in stream:
        if chunk.delta:
            text_parts.append(chunk.delta)
            if on_delta is not None:
                await on_delta(chunk.delta)
        if chunk.tool_calls:
            for call in chunk.tool_calls:
                normalized = dict(call)
                normalized.setdefault("id", str(uuid4()))
                if "function" in normalized and "name" not in normalized:
                    fn = normalized.get("function") or {}
                    normalized["name"] = fn.get("name")
                    normalized["arguments"] = fn.get("arguments") or {}
                tool_calls.append(normalized)
        if chunk.usage is not None:
            usage["input_tokens"] = chunk.usage.input_tokens
            usage["output_tokens"] = chunk.usage.output_tokens
    return {
        "role": "assistant",
        "content": "".join(text_parts),
        "tool_calls": tool_calls,
        "usage": usage,
    }


__all__ = ["complete_chat"]
