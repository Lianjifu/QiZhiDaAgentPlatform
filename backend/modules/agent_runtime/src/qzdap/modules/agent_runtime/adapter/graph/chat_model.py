"""Stream assistant text immediately; assemble tool fragments before execution."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import aclosing
from typing import Any
from uuid import uuid4

from qzdap_llm.client import ChatMessage, ChatRequest
from qzdap_schema.ids import ModelId
from qzdap_vault.actor import ActorContext

from qzdap.modules.agent_runtime.application.ports import LLMPort

DeltaCallback = Callable[[str], Awaitable[None]]


class ToolCallAccumulator:
    """Merge indexed wire deltas without executing partial/duplicate calls."""

    def __init__(self) -> None:
        self._calls: dict[object, dict[str, Any]] = {}
        self._ids: dict[str, object] = {}

    def add(self, calls: list[dict[str, Any]]) -> None:
        for position, call in enumerate(calls):
            call_id = call.get("id")
            key = call.get("index")
            if key is None:
                key = self._ids.get(str(call_id), str(call_id)) if call_id else position
            target = self._calls.setdefault(key, {"id": None, "name": "", "arguments": ""})
            if call_id:
                target["id"] = call_id
                self._ids[str(call_id)] = key
            if call.get("thought_signature"):
                target["thought_signature"] = call["thought_signature"]
            fn = call.get("function") or call
            name = fn.get("name")
            if name:
                target["name"] += str(name)
            args = fn.get("arguments")
            if isinstance(args, str):
                if not isinstance(target["arguments"], str):
                    raise TypeError("mixed tool argument representations")
                target["arguments"] += args
            elif isinstance(args, dict):
                if not target["arguments"]:
                    target["arguments"] = {}
                if not isinstance(target["arguments"], dict):
                    raise TypeError("mixed tool argument representations")
                target["arguments"].update(args)

    def finish(self) -> list[dict[str, Any]]:
        return [
            {
                "id": call["id"] or str(uuid4()),
                "type": "function",
                "name": call["name"],
                "arguments": call["arguments"] or {},
                **({"thought_signature": call["thought_signature"]} if "thought_signature" in call else {}),
                "function": {
                    "name": call["name"],
                    "arguments": call["arguments"] or {},
                },
            }
            for call in self._calls.values()
        ]


async def stream_chat(
    llm: LLMPort,
    *,
    model: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    model_id: ModelId | None = None,
    actor: ActorContext | None = None,
) -> AsyncIterator[str | dict[str, Any]]:
    """Yield content deltas followed by one completed assistant message."""
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
    tool_calls = ToolCallAccumulator()
    usage: dict[str, int] = {"input_tokens": 0, "output_tokens": 0}
    # Preserve the default-port call shape for legacy implementations.
    stream = llm.stream(req, model_id=model_id, actor=actor) if model_id is not None else llm.stream(req)
    async with aclosing(stream):
        async for chunk in stream:
            if chunk.delta:
                text_parts.append(chunk.delta)
                yield chunk.delta
            if chunk.tool_calls:
                tool_calls.add(chunk.tool_calls)
            if chunk.usage is not None:
                usage["input_tokens"] = chunk.usage.input_tokens
                usage["output_tokens"] = chunk.usage.output_tokens
    yield {
        "role": "assistant",
        "content": "".join(text_parts),
        "tool_calls": tool_calls.finish(),
        "usage": usage,
    }


async def complete_chat(
    llm: LLMPort,
    *,
    model: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    model_id: ModelId | None = None,
    actor: ActorContext | None = None,
    on_delta: DeltaCallback | None = None,
) -> dict[str, Any]:
    stream = stream_chat(llm, model=model, messages=messages, tools=tools, model_id=model_id, actor=actor)
    async with aclosing(stream):
        async for event in stream:
            if isinstance(event, dict):
                return event
            if on_delta is not None:
                await on_delta(event)
    raise RuntimeError("LLM stream ended without an assistant message")


__all__ = ["ToolCallAccumulator", "complete_chat", "stream_chat"]
