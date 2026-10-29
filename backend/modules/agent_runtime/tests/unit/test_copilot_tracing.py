"""Tracing tests for the Copilot turn path.

Asserts the span tree the APM shows for one chat turn:

    http.chat.stream          <- HTTP 层, 整个请求
      └── agent.turn          <- 一轮对话
            ├── agent.llm     <- 每次模型调用
            └── agent.tool    <- 每次工具调用

The spans are collected with an in-memory exporter, so no collector is needed.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID

import pytest
from _ar_unit_in_memory import (
    InMemoryIdempotencyStore,
    InMemorySessionJournal,
    make_dependencies,
)
from opentelemetry import trace as otel_trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from qzdap_agent_runtime.gateway.facade import Gateway
from qzdap_agent_runtime.gateway.idempotency import IdempotencyGuard
from qzdap_agent_runtime.gateway.types import ChannelType
from qzdap_agent_runtime.gateway.web import WebChatNormalizer, WebIdentityVerifier
from qzdap_llm.client import ChatRequest, LLMChunk, Usage
from qzdap_schema.ids import AgentId, TenantId, UserId, WorkspaceId

from qzdap.modules.agent_runtime.adapter.graph.runner import SessionGraphRunner
from qzdap.modules.agent_runtime.application.copilot import CopilotSessionService
from qzdap.modules.agent_runtime.domain.catalog import CatalogAgent


class _Catalog:
    def __init__(self, agent: CatalogAgent) -> None:
        self._agent = agent

    async def get_published(self, agent_id):
        return self._agent


class _Messages:
    def __init__(self) -> None:
        self.rows: list[dict] = []

    async def list_for_session(self, session_id):
        return self.rows

    async def append(self, **kwargs):
        self.rows.append(kwargs)


class _ToolLLM:
    """One assistant message that calls a tool, then a final message."""

    def __init__(self) -> None:
        self.requests: list[ChatRequest] = []

    async def stream(self, req: ChatRequest) -> AsyncIterator[LLMChunk]:
        self.requests.append(req)
        yield LLMChunk(
            model=req.model,
            delta="",
            tool_calls=[{"id": "call-1", "name": "echo_tool", "arguments": {"x": 1}}],
        )
        yield LLMChunk(
            model=req.model,
            delta="done",
            finish_reason="stop",
            usage=Usage(input_tokens=1, output_tokens=1),
        )

    async def synthetic_chunks(self, user_input, *, turn_id):
        return []


class _ToolPort:
    def __init__(self) -> None:
        self.invoked: list[tuple[str, dict]] = []

    async def invoke(self, *, call_id, tool_name, arguments):
        self.invoked.append((tool_name, arguments))
        return {"ok": True, "output": "tool output"}

    async def list_tools(self):
        return [{"name": "echo_tool", "description": "echo", "parameters": {}}]


_EXPORTER = InMemorySpanExporter()
# OTel 的全局 TracerProvider 只能设一次, 所以这里在模块加载时设好,
# 每个用例只把 exporter 清空.
_provider = TracerProvider()
_provider.add_span_processor(SimpleSpanProcessor(_EXPORTER))
otel_trace.set_tracer_provider(_provider)


@pytest.fixture
def spans():
    """Collect every span produced during the test."""
    _EXPORTER.clear()
    try:
        yield _EXPORTER
    finally:
        _EXPORTER.clear()


def _by_name(exporter: InMemorySpanExporter) -> dict[str, list]:
    out: dict[str, list] = {}
    for span in exporter.get_finished_spans():
        out.setdefault(span.name, []).append(span)
    return out


async def _make_service(agent: CatalogAgent, owner_id: UserId):
    deps = make_dependencies()
    runner = SessionGraphRunner(llm=_ToolLLM(), tool_port=_ToolPort())
    svc = CopilotSessionService(
        sessions=deps["sessions"],
        turns=deps["turns"],
        messages=_Messages(),
        catalog=_Catalog(agent),
        events=deps["events"],
        graph=runner,
        idempotency=IdempotencyGuard(InMemoryIdempotencyStore()),
        journal=InMemorySessionJournal(),
    )
    tid = TenantId(agent.tenant_id)
    wid = WorkspaceId(agent.workspace_id)
    detail = await svc.create_session(
        tenant_id=tid, workspace_id=wid, owner_id=owner_id, agent_id=agent.id
    )
    return svc, detail["id"], tid, wid


def _agent() -> CatalogAgent:
    agent = CatalogAgent.create(
        id=AgentId(UUID(int=4)),
        tenant_id=TenantId(UUID(int=1)),
        workspace_id=WorkspaceId(UUID(int=2)),
        name="t",
        category="test",
        owner="test",
        model="default",
    )
    agent.tools = [{"name": "echo_tool", "enabled": True}]
    return agent


@pytest.mark.asyncio
async def test_the_llm_and_tool_spans_are_children_of_the_turn_span(spans) -> None:
    agent = _agent()
    svc, sid, tid, wid = await _make_service(agent, UserId(UUID(int=3)))

    _ = [
        chunk
        async for chunk in svc.stream_turn(
            tenant_id=tid,
            workspace_id=wid,
            owner_id=UserId(UUID(int=3)),
            session_id=UUID(sid),
            user_input="hi",
        )
    ]

    named = _by_name(spans)
    assert "agent.turn" in named, "agent.turn span missing"
    assert "agent.llm" in named, "agent.llm span missing"
    assert "agent.tool" in named, "agent.tool span missing"

    turn = named["agent.turn"][0]
    for child_name in ("agent.llm", "agent.tool"):
        child = named[child_name][0]
        assert child.parent is not None, f"{child_name} has no parent"
        assert child.parent.span_id == turn.context.span_id, (
            f"{child_name} is not a child of agent.turn"
        )


@pytest.mark.asyncio
async def test_the_turn_span_hangs_under_the_http_span(spans) -> None:
    agent = _agent()
    owner_id = UserId(UUID(int=3))
    svc, sid, tid, wid = await _make_service(agent, owner_id)

    # HTTP 层建父 span, 把 context 传下去 —— 这一轮要挂在它下面.
    http_span = otel_trace.get_tracer("test.http").start_span("http.chat.stream")
    ctx = otel_trace.set_span_in_context(http_span)
    http_span.end()

    _ = [
        chunk
        async for chunk in svc.stream_turn(
            tenant_id=tid,
            workspace_id=wid,
            owner_id=owner_id,
            session_id=UUID(sid),
            user_input="hi",
            parent_span_context=ctx,
        )
    ]

    turn = _by_name(spans)["agent.turn"][0]
    assert turn.parent is not None, "agent.turn has no parent"
    assert turn.parent.span_id == http_span.context.span_id


@pytest.mark.asyncio
async def test_the_turn_span_records_the_turn_identity(spans) -> None:
    agent = _agent()
    owner_id = UserId(UUID(int=3))
    svc, sid, tid, wid = await _make_service(agent, owner_id)

    _ = [
        chunk
        async for chunk in svc.stream_turn(
            tenant_id=tid,
            workspace_id=wid,
            owner_id=owner_id,
            session_id=UUID(sid),
            user_input="hi",
        )
    ]

    turn = _by_name(spans)["agent.turn"][0]
    assert turn.attributes["agent.session_id"] == sid
    assert turn.attributes["agent.tenant_id"] == str(tid)
    assert turn.attributes["agent.model"]


@pytest.mark.asyncio
async def test_the_http_router_creates_the_parent_span(spans) -> None:
    """The router must open ``http.chat.stream`` and hang the turn under it."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from qzdap.modules.agent_runtime.adapter.http.session_router import (
        build_session_router,
        copilot_dependency,
    )

    agent = _agent()
    owner_id = UserId(UUID(int=3))
    svc, sid, tid, wid = await _make_service(agent, owner_id)

    app = FastAPI()
    app.include_router(build_session_router())
    app.dependency_overrides[copilot_dependency] = lambda: svc
    # web 入口的门面（①②③ + ④）—— 与生产装配同型。
    app.state.web_gateway = Gateway(
        channels=None,
        identity=WebIdentityVerifier(),
        normalizers={ChannelType.WEB: WebChatNormalizer()},
        idempotency=IdempotencyGuard(InMemoryIdempotencyStore()),
    )

    headers = {
        "X-Tenant-Id": str(tid),
        "X-Workspace-Id": str(wid),
        "X-User-Id": str(owner_id),
    }
    with TestClient(app) as client:
        resp = client.post(
            f"/api/sessions/{sid}/turns/stream",
            json={"content": "hi"},
            headers=headers,
        )
        assert resp.status_code == 200

    named = _by_name(spans)
    assert "http.chat.stream" in named, "http.chat.stream span missing"
    http_span = named["http.chat.stream"][0]
    assert http_span.attributes["http.method"] == "POST"
    assert http_span.attributes["session.id"] == sid
    # 一轮对话挂在这个 HTTP span 底下
    assert "agent.turn" in named, "agent.turn span missing"
    turn = named["agent.turn"][0]
    assert turn.parent is not None
    assert turn.parent.span_id == http_span.context.span_id
