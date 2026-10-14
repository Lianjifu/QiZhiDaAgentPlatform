"""Native Anthropic Messages adapter (also explicit Messages-compatible hosts)."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx

from qzdap_llm.client import ChatMessage, ChatRequest, ChatResponse, LLMChunk, Usage
from qzdap_llm.config import LLMConfig
from qzdap_llm.transport import HTTPProviderClient, ProviderTransportError


def _usage(data: dict) -> Usage:
    return Usage(
        data.get("input_tokens", 0),
        data.get("output_tokens", 0),
        data.get("cache_read_input_tokens", 0),
        data.get("cache_creation_input_tokens", 0),
    )


def _finish(reason: str | None) -> str | None:
    if reason is None:
        return None
    return {
        "end_turn": "stop",
        "stop_sequence": "stop",
        "max_tokens": "length",
        "tool_use": "tool_calls",
    }.get(reason, reason)


def _payload(req: ChatRequest, *, stream: bool) -> dict:
    messages: list[dict] = []
    system: list[dict] = []
    for message in req.messages:
        if message.role == "system":
            system.append({"type": "text", "text": message.content})
            continue
        blocks: list[dict] = []
        role = "assistant" if message.role == "assistant" else "user"
        if message.role == "tool":
            blocks.append(
                {
                    "type": "tool_result",
                    "tool_use_id": message.tool_call_id,
                    "content": message.content,
                }
            )
        else:
            if message.content:
                blocks.append({"type": "text", "text": message.content})
            for tool in message.tool_calls or []:
                function = tool["function"]
                blocks.append(
                    {
                        "type": "tool_use",
                        "id": tool["id"],
                        "name": function["name"],
                        "input": json.loads(function["arguments"]),
                    }
                )
        if messages and messages[-1]["role"] == role:
            messages[-1]["content"].extend(blocks)
        else:
            messages.append({"role": role, "content": blocks})
    out = {
        "model": req.model,
        "messages": messages,
        "max_tokens": req.max_tokens or 4096,
        "temperature": req.temperature,
        "stream": stream,
    }
    if system:
        out["system"] = system
    if req.top_p is not None:
        out["top_p"] = req.top_p
    if req.stop:
        out["stop_sequences"] = req.stop
    if req.tools:
        out["tools"] = [
            {
                "name": t["function"]["name"],
                "description": t["function"].get("description", ""),
                "input_schema": t["function"].get("parameters", {"type": "object"}),
            }
            for t in req.tools
        ]
    if req.tool_choice is not None:
        choice = req.tool_choice
        out["tool_choice"] = (
            {"type": {"required": "any"}.get(choice, choice)}
            if isinstance(choice, str)
            else {"type": "tool", "name": choice["function"]["name"]}
        )
    if req.response_format:
        raise ValueError("Anthropic response_format is not supported by this adapter")
    return out


class AnthropicClient(HTTPProviderClient):
    name = "anthropic"

    def __init__(self, config: LLMConfig, *, http: httpx.AsyncClient | None = None):
        super().__init__(
            base_url=config.base_url,
            headers={"x-api-key": config.api_key, "anthropic-version": "2023-06-01"},
            timeout_seconds=config.timeout_seconds,
            http=http,
        )

    @property
    def _path(self) -> str:
        return "messages" if self._base_url.endswith("/v1") else "v1/messages"

    async def chat(self, req: ChatRequest) -> ChatResponse:
        data = await self._post(self._path, _payload(req, stream=False))
        try:
            text = "".join(b["text"] for b in data["content"] if b["type"] == "text")
            tools = [
                {
                    "id": b["id"],
                    "type": "function",
                    "function": {
                        "name": b["name"],
                        "arguments": json.dumps(b["input"]),
                    },
                }
                for b in data["content"]
                if b["type"] == "tool_use"
            ]
            return ChatResponse(
                data["model"],
                ChatMessage("assistant", text, tool_calls=tools or None),
                _finish(data.get("stop_reason")) or "stop",
                _usage(data.get("usage", {})),
                data,
            )
        except (KeyError, TypeError, ValueError, AttributeError):
            raise ProviderTransportError(code="LLM_INVALID_RESPONSE") from None

    async def stream(self, req: ChatRequest) -> AsyncIterator[LLMChunk]:
        events = self._events(self._path, _payload(req, stream=True))
        model = req.model
        usage: dict = {}
        tool_indices: dict[int, int] = {}
        tool_has_arguments: set[int] = set()
        try:
            async for event, data in events:
                kind = data.get("type", event)
                try:
                    if kind == "message_start":
                        model = data["message"].get("model", model)
                        usage.update(data["message"].get("usage", {}))
                        yield LLMChunk(model, "", usage=_usage(usage))
                    elif kind == "content_block_start":
                        block = data["content_block"]
                        if block["type"] == "tool_use":
                            index = len(tool_indices)
                            tool_indices[data["index"]] = index
                            arguments = (
                                json.dumps(block["input"]) if block.get("input") else ""
                            )
                            if arguments:
                                tool_has_arguments.add(data["index"])
                            yield LLMChunk(
                                model,
                                "",
                                tool_calls=[
                                    {
                                        "index": index,
                                        "id": block["id"],
                                        "type": "function",
                                        "function": {
                                            "name": block["name"],
                                            "arguments": arguments,
                                        },
                                    }
                                ],
                            )
                        elif block["type"] == "text" and block.get("text"):
                            yield LLMChunk(model, block["text"])
                    elif kind == "content_block_delta":
                        delta = data["delta"]
                        if delta["type"] == "text_delta":
                            yield LLMChunk(model, delta["text"])
                        elif delta["type"] == "input_json_delta":
                            if delta["partial_json"]:
                                tool_has_arguments.add(data["index"])
                            yield LLMChunk(
                                model,
                                "",
                                tool_calls=[
                                    {
                                        "index": tool_indices[data["index"]],
                                        "function": {
                                            "arguments": delta["partial_json"]
                                        },
                                    }
                                ],
                            )
                    elif kind == "content_block_stop":
                        block_index = data["index"]
                        if (
                            block_index in tool_indices
                            and block_index not in tool_has_arguments
                        ):
                            yield LLMChunk(
                                model,
                                "",
                                tool_calls=[
                                    {
                                        "index": tool_indices[block_index],
                                        "function": {"arguments": "{}"},
                                    }
                                ],
                            )
                    elif kind == "message_delta":
                        usage.update(data.get("usage", {}))
                        yield LLMChunk(
                            model,
                            "",
                            finish_reason=_finish(data["delta"].get("stop_reason")),
                            usage=_usage(usage),
                        )
                    elif kind == "message_stop":
                        return
                except (KeyError, TypeError, ValueError, AttributeError):
                    raise ProviderTransportError(code="LLM_INVALID_RESPONSE") from None
        finally:
            await events.aclose()
