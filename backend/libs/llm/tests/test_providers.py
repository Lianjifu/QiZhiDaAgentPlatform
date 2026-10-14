"""Provider wire contracts, using injected HTTP transports only."""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from qzdap_llm import (
    ChatMessage,
    ChatRequest,
    LLMChunk,
    LLMClient,
    LLMRouter,
    ProviderTransportError,
    build_provider_client,
    get_provider_spec,
    list_provider_specs,
)
from qzdap_llm.openai_compatible import OpenAICompatibleClient

TOOL = {
    "type": "function",
    "function": {
        "name": "weather",
        "description": "Weather",
        "parameters": {"type": "object", "properties": {"city": {"type": "string"}}},
    },
}
CALL = {
    "id": "call_a",
    "type": "function",
    "function": {"name": "weather", "arguments": '{"city":"Paris"}'},
}
REQUEST = ChatRequest(
    model="test-model",
    messages=[
        ChatMessage("system", "Be concise"),
        ChatMessage("user", "Weather?"),
        ChatMessage("assistant", "", tool_calls=[CALL]),
        ChatMessage("tool", '{"temp":18}', tool_call_id="call_a"),
        ChatMessage("user", "Thanks"),
    ],
    tools=[TOOL],
    tool_choice="auto",
    max_tokens=32,
    top_p=0.8,
    stop=["END"],
)
OPENAI_RESPONSE = {
    "model": "test-model",
    "choices": [
        {
            "message": {"role": "assistant", "content": "Sunny", "tool_calls": [CALL]},
            "finish_reason": "tool_calls",
        }
    ],
    "usage": {
        "prompt_tokens": 10,
        "completion_tokens": 4,
        "prompt_tokens_details": {"cached_tokens": 3},
    },
}
ANTHROPIC_RESPONSE = {
    "model": "test-model",
    "content": [
        {"type": "text", "text": "Sunny"},
        {
            "type": "tool_use",
            "id": "call_a",
            "name": "weather",
            "input": {"city": "Paris"},
        },
    ],
    "stop_reason": "tool_use",
    "usage": {
        "input_tokens": 10,
        "output_tokens": 4,
        "cache_read_input_tokens": 3,
        "cache_creation_input_tokens": 2,
    },
}
GOOGLE_RESPONSE = {
    "modelVersion": "test-model",
    "candidates": [
        {
            "content": {
                "role": "model",
                "parts": [
                    {"text": "Sunny"},
                    {
                        "functionCall": {
                            "id": "call_a",
                            "name": "weather",
                            "args": {"city": "Paris"},
                        },
                        "thoughtSignature": "signature",
                    },
                ],
            },
            "finishReason": "STOP",
        }
    ],
    "usageMetadata": {
        "promptTokenCount": 10,
        "candidatesTokenCount": 4,
        "cachedContentTokenCount": 3,
    },
}


def response_for(protocol):
    return {
        "anthropic": ANTHROPIC_RESPONSE,
        "anthropic-compatible": ANTHROPIC_RESPONSE,
        "google": GOOGLE_RESPONSE,
    }.get(protocol, OPENAI_RESPONSE)


def make_client(protocol, handler, **kwargs):
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    defaults = (
        {"base_url": "https://region.example/api"}
        if get_provider_spec(protocol).requires_base_url
        else {}
    )
    if protocol == "azure":
        defaults["api_version"] = "2024-10-21"
    defaults.update(kwargs)
    return build_provider_client(
        protocol=protocol, api_key="secret-key", http=http, **defaults
    ), http


@pytest.mark.parametrize("protocol", [s.protocol for s in list_provider_specs()])
@pytest.mark.asyncio
async def test_registry_chat_wire(protocol):
    captured = []

    def handler(request):
        captured.append(request)
        return httpx.Response(200, json=response_for(protocol))

    client, http = make_client(protocol, handler)
    async with http:
        result = await client.chat(REQUEST)
        assert result.message.content == "Sunny"
        assert result.finish_reason == "tool_calls"
        assert result.message.tool_calls[0]["function"]["name"] == "weather"
        assert json.loads(result.message.tool_calls[0]["function"]["arguments"]) == {
            "city": "Paris"
        }
        assert result.usage.input_tokens == 10
        assert result.usage.output_tokens == 4
        assert result.usage.cache_read_tokens == 3
        request = captured[0]
        body = json.loads(request.content)
        transport = get_provider_spec(protocol).transport
        if transport == "openai":
            assert isinstance(client, OpenAICompatibleClient)
            assert request.headers["authorization"] == "Bearer secret-key"
            assert request.url.path.endswith("/chat/completions")
            assert body["messages"][0] == {"role": "system", "content": "Be concise"}
            assert body["messages"][3]["tool_call_id"] == "call_a"
            assert body["tools"] == [TOOL]
        elif transport == "anthropic":
            assert request.headers["x-api-key"] == "secret-key"
            assert request.headers["anthropic-version"] == "2023-06-01"
            assert request.url.path.endswith("/v1/messages")
            assert "authorization" not in request.headers
            assert body["system"] == [{"type": "text", "text": "Be concise"}]
            assert body["messages"][1]["content"][0]["type"] == "tool_use"
            assert body["messages"][2]["content"][0]["tool_use_id"] == "call_a"
            assert body["messages"][2]["content"][1]["text"] == "Thanks"
            assert body["tools"][0]["input_schema"] == TOOL["function"]["parameters"]
        elif transport == "google":
            assert request.headers["x-goog-api-key"] == "secret-key"
            assert (
                str(request.url)
                == "https://generativelanguage.googleapis.com/v1beta/models/test-model:generateContent"
            )
            assert "secret-key" not in str(request.url)
            assert body["systemInstruction"] == {"parts": [{"text": "Be concise"}]}
            assert body["contents"][1]["role"] == "model"
            assert body["contents"][1]["parts"][0]["functionCall"]["args"] == {
                "city": "Paris"
            }
            assert body["contents"][2]["parts"][0]["functionResponse"] == {
                "id": "call_a",
                "name": "weather",
                "response": {"temp": 18},
            }
            assert body["tools"][0]["functionDeclarations"][0]["name"] == "weather"
            assert body["generationConfig"]["maxOutputTokens"] == 32
        else:
            assert request.headers["api-key"] == "secret-key"
            assert "authorization" not in request.headers
            assert (
                request.url.path
                == "/api/openai/deployments/test-model/chat/completions"
            )
            assert request.url.params["api-version"] == "2024-10-21"
        await client.aclose()
        assert not http.is_closed


@pytest.mark.parametrize(
    "protocol,url,path",
    [
        ("deepseek", "https://api.deepseek.com", "/chat/completions"),
        ("deepseek", "https://api.deepseek.com/v1", "/v1/chat/completions"),
        ("openai", "https://api.openai.com/v1/", "/v1/chat/completions"),
        (
            "glm",
            "https://open.bigmodel.cn/api/paas/v4",
            "/api/paas/v4/chat/completions",
        ),
        ("kimi", "https://api.moonshot.ai/v1", "/v1/chat/completions"),
        ("minimax", "https://api.minimax.io/v1", "/v1/chat/completions"),
        ("anthropic-compatible", "https://custom.example/v1", "/v1/messages"),
    ],
)
@pytest.mark.asyncio
async def test_api_roots_preserved(protocol, url, path):
    def handler(request):
        assert request.url.path == path
        return httpx.Response(200, json=response_for(protocol))

    client, http = make_client(protocol, handler, base_url=url)
    async with http:
        await client.chat(REQUEST)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"protocol": "unknown"},
        {"protocol": "qwen"},
        {"protocol": "azure"},
        {"protocol": "azure", "base_url": "https://azure.example"},
        {"protocol": "openai-compatible"},
        {"protocol": "anthropic-compatible"},
        {"protocol": "openai", "base_url": "https://user:key@example.com/v1"},
        {"protocol": "openai", "base_url": "https://example.com?key=secret"},
        {"protocol": "openai", "timeout_seconds": 0},
    ],
)
def test_factory_rejects_unknown_or_missing_configuration(kwargs):
    with pytest.raises(ValueError):
        build_provider_client(api_key="k", **kwargs)


def sse(events):
    return "".join(
        f"event: {event}\r\ndata:{json.dumps(data)}\r\n\r\n" for event, data in events
    )


OPENAI_EVENTS = [
    ("message", {"model": "test-model", "choices": [{"delta": {"content": "Sun"}}]}),
    (
        "message",
        {
            "model": "test-model",
            "choices": [
                {
                    "delta": {
                        "tool_calls": [
                            {
                                "index": 1,
                                "id": "second",
                                "type": "function",
                                "function": {
                                    "name": "weather",
                                    "arguments": '{"city":',
                                },
                            }
                        ]
                    }
                }
            ],
        },
    ),
    (
        "message",
        {
            "model": "test-model",
            "choices": [
                {
                    "delta": {
                        "tool_calls": [
                            {"index": 1, "function": {"arguments": '"Paris"}'}}
                        ]
                    },
                    "finish_reason": "tool_calls",
                }
            ],
        },
    ),
    (
        "message",
        {"model": "test-model", "choices": [], "usage": OPENAI_RESPONSE["usage"]},
    ),
]
ANTHROPIC_EVENTS = [
    (
        "message_start",
        {
            "type": "message_start",
            "message": {
                "model": "test-model",
                "usage": {"input_tokens": 10, "cache_read_input_tokens": 3},
            },
        },
    ),
    ("ping", {"type": "ping"}),
    (
        "content_block_start",
        {
            "type": "content_block_start",
            "index": 0,
            "content_block": {"type": "text", "text": ""},
        },
    ),
    (
        "content_block_delta",
        {
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "text_delta", "text": "Sun"},
        },
    ),
    (
        "content_block_start",
        {
            "type": "content_block_start",
            "index": 1,
            "content_block": {
                "type": "tool_use",
                "id": "call_a",
                "name": "weather",
                "input": {},
            },
        },
    ),
    (
        "content_block_delta",
        {
            "type": "content_block_delta",
            "index": 1,
            "delta": {"type": "input_json_delta", "partial_json": '{"city":'},
        },
    ),
    (
        "content_block_delta",
        {
            "type": "content_block_delta",
            "index": 1,
            "delta": {"type": "input_json_delta", "partial_json": '"Paris"}'},
        },
    ),
    (
        "message_delta",
        {
            "type": "message_delta",
            "delta": {"stop_reason": "tool_use"},
            "usage": {"output_tokens": 4},
        },
    ),
    ("message_stop", {"type": "message_stop"}),
]
GOOGLE_EVENTS = [
    ("message", {"candidates": [{"content": {"parts": [{"text": "Sun"}]}}]}),
    (
        "message",
        {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "functionCall": {
                                    "id": "call_a",
                                    "name": "weather",
                                    "args": {"city": "Paris"},
                                }
                            }
                        ]
                    }
                }
            ]
        },
    ),
    (
        "message",
        {
            "candidates": [{"finishReason": "STOP"}],
            "usageMetadata": GOOGLE_RESPONSE["usageMetadata"],
        },
    ),
]


@pytest.mark.parametrize("protocol", ["openai", "anthropic", "google", "azure"])
@pytest.mark.asyncio
async def test_stream_tools_usage_and_native_finish(protocol):
    events = {"anthropic": ANTHROPIC_EVENTS, "google": GOOGLE_EVENTS}.get(
        protocol, OPENAI_EVENTS
    )

    def handler(request):
        body = json.loads(request.content)
        if protocol == "google":
            assert request.url.path.endswith(":streamGenerateContent")
            assert request.url.params["alt"] == "sse"
            assert "stream" not in body
        else:
            assert body["stream"] is True
        return httpx.Response(
            200, text=sse(events)
        )  # Native streams end at EOF, not [DONE].

    client, http = make_client(protocol, handler)
    async with http:
        chunks = [chunk async for chunk in client.stream(REQUEST)]
    assert "".join(chunk.delta for chunk in chunks) == "Sun"
    assert (
        next(chunk.finish_reason for chunk in chunks if chunk.finish_reason)
        == "tool_calls"
    )
    assert chunks[-1].usage.input_tokens == 10
    assert chunks[-1].usage.output_tokens == 4
    assert chunks[-1].usage.cache_read_tokens == 3
    tools = [call for chunk in chunks for call in chunk.tool_calls or []]
    assert tools[0]["function"]["name"] == "weather"
    assert tools[0]["type"] == "function"
    assert "id" in tools[0] and "index" in tools[0]
    arguments = "".join(call["function"].get("arguments", "") for call in tools)
    assert json.loads(arguments) == {"city": "Paris"}
    if protocol in ("openai", "azure"):
        assert all(call["index"] == 1 for call in tools)


@pytest.mark.parametrize("protocol", ["openai", "anthropic", "google", "azure"])
@pytest.mark.parametrize("operation", ["chat", "stream"])
@pytest.mark.parametrize("failure", ["status", "network", "invalid", "event_error"])
@pytest.mark.asyncio
async def test_errors_do_not_expose_secrets(protocol, operation, failure):
    secret = "secret-key https://secret.example/path private-body"

    def handler(request):
        if failure == "network":
            raise httpx.ConnectError(secret, request=request)
        if failure == "status":
            return httpx.Response(401, text=secret)
        if failure == "event_error":
            return (
                httpx.Response(200, json={"error": {"message": secret}})
                if operation == "chat"
                else httpx.Response(
                    200, text=sse([("error", {"error": {"message": secret}})])
                )
            )
        return httpx.Response(200, text="not json")

    client, http = make_client(protocol, handler)
    async with http:
        with pytest.raises(ProviderTransportError) as caught:
            if operation == "chat":
                await client.chat(REQUEST)
            else:
                _ = [chunk async for chunk in client.stream(REQUEST)]
    error = caught.value
    assert error.status_code == (401 if failure == "status" else None)
    assert error.status == 502
    assert error.__cause__ is None
    assert error.__context__ is None or error.__suppress_context__
    assert "secret" not in str(error)
    assert "https://" not in str(error)
    assert error.details == {}


class TrackedStream(httpx.AsyncByteStream):
    def __init__(self, data, block=False):
        self.data = data
        self.closed = False
        self.block = block
        self.waiting = asyncio.Event()

    async def __aiter__(self):
        yield self.data.encode()
        if self.block:
            self.waiting.set()
            await asyncio.Event().wait()

    async def aclose(self):
        self.closed = True


@pytest.mark.parametrize("protocol", ["openai", "anthropic", "google", "azure"])
@pytest.mark.parametrize("cancel", [False, True])
@pytest.mark.asyncio
async def test_stream_close_and_cancellation_release_response(protocol, cancel):
    events = {"anthropic": ANTHROPIC_EVENTS[:1], "google": GOOGLE_EVENTS[:1]}.get(
        protocol, OPENAI_EVENTS[:1]
    )
    tracked = TrackedStream(sse(events), block=cancel)
    client, http = make_client(protocol, lambda _: httpx.Response(200, stream=tracked))
    async with http:
        stream = client.stream(REQUEST)
        await anext(stream)
        if cancel:
            task = asyncio.create_task(anext(stream))
            await tracked.waiting.wait()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            await stream.aclose()
        assert tracked.closed
        assert not http.is_closed


@pytest.mark.asyncio
async def test_owned_clients_and_router_lifecycle():
    client = build_provider_client(protocol="openai", api_key="k")
    await LLMRouter(client).aclose()
    assert client._http.is_closed
    await LLMClient().aclose()


@pytest.mark.asyncio
async def test_router_never_replays_midstream_and_closes_iterator():
    closed = []

    class Broken(LLMClient):
        async def stream(self, req):
            try:
                yield LLMChunk(req.model, "first")
                raise ProviderTransportError()
            finally:
                closed.append(True)

    class Other(LLMClient):
        async def stream(self, req):
            pytest.fail("Midstream failure must not fail over")
            yield

    router = LLMRouter(Broken(), [Other()])
    with pytest.raises(ProviderTransportError):
        _ = [chunk async for chunk in router.stream(REQUEST)]
    assert closed == [True]


@pytest.mark.asyncio
async def test_google_signature_replayed_and_tool_result_string():
    captured = []
    client, http = make_client(
        "google",
        lambda r: (
            captured.append(json.loads(r.content))
            or httpx.Response(200, json=GOOGLE_RESPONSE)
        ),
    )
    async with http:
        result = await client.chat(REQUEST)
        req = ChatRequest(
            "models/test-model",
            [
                ChatMessage("user", "hi"),
                result.message,
                ChatMessage("tool", "plain result", tool_call_id="call_a"),
            ],
        )
        await client.chat(req)
    assert captured[1]["contents"][1]["parts"][1]["thoughtSignature"] == "signature"
    assert captured[1]["contents"][2]["parts"][0]["functionResponse"]["response"] == {
        "result": "plain result"
    }


@pytest.mark.parametrize("protocol", ["anthropic", "google"])
@pytest.mark.parametrize(
    "choice",
    ["none", "required", {"type": "function", "function": {"name": "weather"}}],
)
@pytest.mark.asyncio
async def test_native_tool_choice_conversion(protocol, choice):
    captured = []
    client, http = make_client(
        protocol,
        lambda r: (
            captured.append(json.loads(r.content))
            or httpx.Response(200, json=response_for(protocol))
        ),
    )
    async with http:
        await client.chat(
            ChatRequest(
                "m", [ChatMessage("user", "hi")], tools=[TOOL], tool_choice=choice
            )
        )
    body = captured[0]
    if protocol == "anthropic":
        expected = (
            {"type": "tool", "name": "weather"}
            if isinstance(choice, dict)
            else {"type": "any" if choice == "required" else choice}
        )
        assert body["tool_choice"] == expected
    else:
        expected = (
            {"mode": "ANY", "allowedFunctionNames": ["weather"]}
            if isinstance(choice, dict)
            else {"mode": "ANY" if choice == "required" else "NONE"}
        )
        assert body["toolConfig"]["functionCallingConfig"] == expected


@pytest.mark.asyncio
async def test_anthropic_parallel_tools_and_zero_argument_stream():
    events = [
        (
            "content_block_start",
            {
                "type": "content_block_start",
                "index": 2,
                "content_block": {
                    "type": "tool_use",
                    "id": "a",
                    "name": "first",
                    "input": {},
                },
            },
        ),
        ("content_block_stop", {"type": "content_block_stop", "index": 2}),
        (
            "content_block_start",
            {
                "type": "content_block_start",
                "index": 4,
                "content_block": {
                    "type": "tool_use",
                    "id": "b",
                    "name": "second",
                    "input": {},
                },
            },
        ),
        (
            "content_block_delta",
            {
                "type": "content_block_delta",
                "index": 4,
                "delta": {"type": "input_json_delta", "partial_json": '{"ok":true}'},
            },
        ),
        ("content_block_stop", {"type": "content_block_stop", "index": 4}),
        ("message_stop", {"type": "message_stop"}),
    ]
    client, http = make_client(
        "anthropic", lambda _: httpx.Response(200, text=sse(events))
    )
    async with http:
        calls = [
            call
            async for chunk in client.stream(REQUEST)
            for call in chunk.tool_calls or []
        ]
    assert (
        json.loads(
            "".join(
                c["function"].get("arguments", "") for c in calls if c["index"] == 0
            )
        )
        == {}
    )
    assert json.loads(
        "".join(c["function"].get("arguments", "") for c in calls if c["index"] == 1)
    ) == {"ok": True}


@pytest.mark.asyncio
async def test_google_multiple_stream_calls_get_distinct_synthetic_ids():
    events = [
        (
            "message",
            {
                "candidates": [
                    {
                        "content": {
                            "parts": [{"functionCall": {"name": "weather", "args": {}}}]
                        }
                    }
                ]
            },
        )
        for _ in range(2)
    ]
    client, http = make_client(
        "google", lambda _: httpx.Response(200, text=sse(events))
    )
    async with http:
        calls = [
            call
            async for chunk in client.stream(REQUEST)
            for call in chunk.tool_calls or []
        ]
    assert [c["index"] for c in calls] == [0, 1]
    assert len({c["id"] for c in calls}) == 2


@pytest.mark.parametrize("protocol", ["openai", "azure"])
@pytest.mark.asyncio
async def test_embeddings_and_azure_openai_root(protocol):
    def handler(request):
        if protocol == "azure":
            assert (
                request.url.path
                == "/openai/deployments/text-embedding-3-small/embeddings"
            )
            assert request.headers["api-key"] == "secret-key"
        else:
            assert request.url.path == "/v1/embeddings"
        assert json.loads(request.content)["input"] == ["one"]
        return httpx.Response(200, json={"data": [{"embedding": [0.5, 1.0]}]})

    kwargs = {"base_url": "https://azure.example/openai"} if protocol == "azure" else {}
    client, http = make_client(protocol, handler, **kwargs)
    async with http:
        assert await client.embed(["one"]) == [[0.5, 1.0]]


@pytest.mark.asyncio
async def test_sse_multiline_comments_eof_done_and_stream_options():
    from qzdap_llm.transport import iter_sse

    response = httpx.Response(
        200,
        text=': ping\r\nevent: message\r\ndata: {\r\ndata: "ok": true}\r\n\r\ndata: last',
    )
    assert [item async for item in iter_sse(response)] == [
        ("message", '{\n"ok": true}'),
        ("message", "last"),
    ]

    def handler(request):
        assert json.loads(request.content)["stream_options"] == {"include_usage": True}
        return httpx.Response(
            200, text=sse(OPENAI_EVENTS[:1]) + "data: [DONE]\n\n" + "data: invalid\n\n"
        )

    client, http = make_client("openai", handler)
    async with http:
        assert len([chunk async for chunk in client.stream(REQUEST)]) == 1


@pytest.mark.parametrize("protocol", ["openai", "anthropic", "google"])
@pytest.mark.asyncio
async def test_malformed_nested_response_is_sanitized(protocol):
    malformed = {
        "openai": {"model": "x", "choices": [None]},
        "anthropic": {"model": "x", "content": [None]},
        "google": {"candidates": [None]},
    }[protocol]
    client, http = make_client(protocol, lambda _: httpx.Response(200, json=malformed))
    async with http:
        with pytest.raises(ProviderTransportError):
            await client.chat(REQUEST)
