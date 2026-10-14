"""Google Gemini native generateContent and streaming transport."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from urllib.parse import quote

import httpx

from qzdap_llm.client import ChatMessage, ChatRequest, ChatResponse, LLMChunk, Usage
from qzdap_llm.config import LLMConfig
from qzdap_llm.transport import HTTPProviderClient, ProviderTransportError


def _usage(data: dict) -> Usage:
    return Usage(
        data.get("promptTokenCount", 0),
        data.get("candidatesTokenCount", 0),
        data.get("cachedContentTokenCount", 0),
    )


def _finish(candidate: dict) -> str | None:
    reason = candidate.get("finishReason")
    if reason == "STOP":
        return (
            "tool_calls"
            if any(
                "functionCall" in p
                for p in candidate.get("content", {}).get("parts", [])
            )
            else "stop"
        )
    if reason is None:
        return None
    return {
        "MAX_TOKENS": "length",
        "SAFETY": "content_filter",
        "RECITATION": "content_filter",
    }.get(reason, reason)


def _payload(req: ChatRequest) -> dict:
    contents: list[dict] = []
    systems: list[dict] = []
    names: dict[str, str] = {}
    for message in req.messages:
        if message.role == "system":
            systems.append({"text": message.content})
            continue
        parts: list[dict] = []
        role = "model" if message.role == "assistant" else "user"
        if message.role == "tool":
            name = message.name or names.get(message.tool_call_id or "")
            if not name:
                raise ValueError("Google tool results require a matching function name")
            try:
                result = json.loads(message.content)
            except ValueError:
                result = message.content
            response = result if isinstance(result, dict) else {"result": result}
            function_response = {"name": name, "response": response}
            if message.tool_call_id:
                function_response["id"] = message.tool_call_id
            parts.append({"functionResponse": function_response})
        else:
            if message.content:
                parts.append({"text": message.content})
            for call in message.tool_calls or []:
                function = call["function"]
                names[call["id"]] = function["name"]
                native = {
                    "functionCall": {
                        "id": call["id"],
                        "name": function["name"],
                        "args": json.loads(function["arguments"]),
                    }
                }
                if call.get("thought_signature"):
                    native["thoughtSignature"] = call["thought_signature"]
                parts.append(native)
        if contents and contents[-1]["role"] == role:
            contents[-1]["parts"].extend(parts)
        else:
            contents.append({"role": role, "parts": parts})
    generation: dict = {"temperature": req.temperature}
    if req.max_tokens is not None:
        generation["maxOutputTokens"] = req.max_tokens
    if req.top_p is not None:
        generation["topP"] = req.top_p
    if req.stop:
        generation["stopSequences"] = req.stop
    if req.response_format:
        kind = req.response_format.get("type")
        if kind not in ("json_object", "json_schema"):
            raise ValueError("Unsupported Google response format")
        generation["responseMimeType"] = "application/json"
        if kind == "json_schema":
            generation["responseJsonSchema"] = req.response_format["json_schema"][
                "schema"
            ]
    out = {"contents": contents, "generationConfig": generation}
    if systems:
        out["systemInstruction"] = {"parts": systems}
    if req.tools:
        out["tools"] = [
            {
                "functionDeclarations": [
                    {
                        "name": t["function"]["name"],
                        "description": t["function"].get("description", ""),
                        "parametersJsonSchema": t["function"].get(
                            "parameters", {"type": "object"}
                        ),
                    }
                    for t in req.tools
                ]
            }
        ]
    if req.tool_choice is not None:
        choice = req.tool_choice
        config = (
            {
                "mode": {"auto": "AUTO", "none": "NONE", "required": "ANY"}.get(
                    choice, "AUTO"
                )
            }
            if isinstance(choice, str)
            else {"mode": "ANY", "allowedFunctionNames": [choice["function"]["name"]]}
        )
        out["toolConfig"] = {"functionCallingConfig": config}
    return out


def _parse(data: dict, model: str, *, tool_offset: int = 0) -> ChatResponse:
    candidates = data.get("candidates") or []
    if not candidates:
        raise ProviderTransportError(code="LLM_INVALID_RESPONSE")
    candidate = candidates[0]
    parts = candidate.get("content", {}).get("parts", [])
    text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
    calls: list[dict] = []
    for part in parts:
        if "functionCall" in part:
            function = part["functionCall"]
            call = {
                "id": function.get("id") or f"google_call_{tool_offset + len(calls)}",
                "type": "function",
                "function": {
                    "name": function["name"],
                    "arguments": json.dumps(function.get("args", {})),
                },
            }
            if part.get("thoughtSignature"):
                call["thought_signature"] = part["thoughtSignature"]
            calls.append(call)
    return ChatResponse(
        data.get("modelVersion", model),
        ChatMessage("assistant", text, tool_calls=calls or None),
        _finish(candidate) or "stop",
        _usage(data.get("usageMetadata", {})),
        data,
    )


class GoogleClient(HTTPProviderClient):
    name = "google"

    def __init__(self, config: LLMConfig, *, http: httpx.AsyncClient | None = None):
        super().__init__(
            base_url=config.base_url,
            headers={"x-goog-api-key": config.api_key},
            timeout_seconds=config.timeout_seconds,
            http=http,
        )

    def _path(self, model: str, *, stream: bool) -> str:
        model = model.removeprefix("models/")
        action = "streamGenerateContent?alt=sse" if stream else "generateContent"
        return f"models/{quote(model, safe='')}:{action}"

    async def chat(self, req: ChatRequest) -> ChatResponse:
        data = await self._post(self._path(req.model, stream=False), _payload(req))
        try:
            return _parse(data, req.model)
        except (KeyError, TypeError, ValueError, AttributeError, IndexError):
            raise ProviderTransportError(code="LLM_INVALID_RESPONSE") from None

    async def stream(self, req: ChatRequest) -> AsyncIterator[LLMChunk]:
        events = self._events(self._path(req.model, stream=True), _payload(req))
        tool_count = 0
        saw_tools = False
        try:
            async for _, data in events:
                try:
                    if not data.get("candidates"):
                        if data.get("usageMetadata"):
                            yield LLMChunk(
                                req.model, "", usage=_usage(data["usageMetadata"])
                            )
                            continue
                        raise ProviderTransportError(code="LLM_INVALID_RESPONSE")
                    parsed = _parse(data, req.model, tool_offset=tool_count)
                    calls = [
                        {"index": tool_count + i, **call}
                        for i, call in enumerate(parsed.message.tool_calls or [])
                    ]
                    tool_count += len(calls)
                    saw_tools = saw_tools or bool(calls)
                    reason = _finish(data["candidates"][0])
                    if reason == "stop" and saw_tools:
                        reason = "tool_calls"
                    yield LLMChunk(
                        parsed.model,
                        parsed.message.content,
                        finish_reason=reason,
                        tool_calls=calls or None,
                        usage=parsed.usage if "usageMetadata" in data else None,
                    )
                except (KeyError, TypeError, ValueError, AttributeError, IndexError):
                    raise ProviderTransportError(code="LLM_INVALID_RESPONSE") from None
        finally:
            await events.aclose()
