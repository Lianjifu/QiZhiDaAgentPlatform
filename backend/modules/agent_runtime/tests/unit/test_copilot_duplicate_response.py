"""重复请求的**无感重放** —— 重放事件流，而不是 202 降级（Gateway §4.5 / Stage 4b）。

**验收**（§10 Stage 4b）：SSE 断开后带 ``Last-Event-ID`` 重连 → **重放拼接结果
与原流 chunk 序列的 hash 相同**、seq 连续；重放**不再走 202 降级路径**。

**不得静默丢弃重复请求** —— 客户端必须知道「这一轮到底跑没跑」：能重放就重放，
重放不了（这一轮还没落过事件 / 还在跑）才回 409。
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from uuid import UUID

import pytest
from _ar_unit_in_memory import (
    InMemoryIdempotencyStore,
    InMemorySessionJournal,
    make_dependencies,
)
from fastapi import FastAPI
from fastapi.testclient import TestClient
from qzdap_agent_runtime.gateway.facade import Gateway
from qzdap_agent_runtime.gateway.idempotency import IdempotencyGuard
from qzdap_agent_runtime.gateway.replay import StoredEvent, event_digest
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

    async def get_published(self, agent_id):  # type: ignore[no-untyped-def]
        return self._agent


class _Messages:
    def __init__(self) -> None:
        self.rows: list[dict] = []

    async def list_for_session(self, session_id):  # type: ignore[no-untyped-def]
        return self.rows

    async def append(self, **kwargs):  # type: ignore[no-untyped-def]
        self.rows.append(kwargs)


class _LLM:
    """一轮就回一句话。"""

    def __init__(self) -> None:
        self.requests: list[ChatRequest] = []

    async def stream(self, req: ChatRequest) -> AsyncIterator[LLMChunk]:
        self.requests.append(req)
        yield LLMChunk(
            model=req.model,
            delta="hi back",
            finish_reason="stop",
            usage=Usage(input_tokens=1, output_tokens=1),
        )

    async def synthetic_chunks(self, user_input, *, turn_id):  # type: ignore[no-untyped-def]
        return []


def _agent() -> CatalogAgent:
    return CatalogAgent.create(
        id=AgentId(UUID(int=4)),
        tenant_id=TenantId(UUID(int=1)),
        workspace_id=WorkspaceId(UUID(int=2)),
        name="t",
        category="test",
        owner="test",
        model="default",
    )


def _chunk_payloads(body: str) -> list[dict]:
    """抽出 SSE 响应体里的 **chunk 载荷**（跳过 ``data: {}`` 的结束帧）。"""
    out = []
    for frame in body.split("\n\n"):
        for line in frame.splitlines():
            if not line.startswith("data: "):
                continue
            payload = json.loads(line[len("data: ") :])
            if "kind" in payload:
                out.append(payload)
    return out


def _events(body: str) -> list[StoredEvent]:
    """SSE 帧 → 事件（SSE 帧与事件同形：``id`` / ``event`` / ``data``）。"""
    return [
        StoredEvent(
            seq=int(payload["seq"]),
            event_type=str(payload["kind"]),
            payload=payload,
        )
        for payload in _chunk_payloads(body)
    ]


async def _make_service(agent: CatalogAgent, owner_id: UserId):  # type: ignore[no-untyped-def]
    deps = make_dependencies()
    svc = CopilotSessionService(
        sessions=deps["sessions"],
        turns=deps["turns"],
        messages=_Messages(),
        catalog=_Catalog(agent),
        events=deps["events"],
        graph=SessionGraphRunner(llm=_LLM()),
        idempotency=IdempotencyGuard(InMemoryIdempotencyStore()),
        journal=InMemorySessionJournal(),
    )
    tid = TenantId(agent.tenant_id)
    wid = WorkspaceId(agent.workspace_id)
    detail = await svc.create_session(
        tenant_id=tid, workspace_id=wid, owner_id=owner_id, agent_id=agent.id
    )
    return svc, detail["id"], tid, wid


def _app(svc: CopilotSessionService, journal) -> FastAPI:  # type: ignore[no-untyped-def]
    from qzdap.modules.agent_runtime.adapter.http.session_router import (
        build_session_router,
        copilot_dependency,
    )

    app = FastAPI()
    app.include_router(build_session_router())
    app.dependency_overrides[copilot_dependency] = lambda: svc
    # web 入口的门面（①②③ + ④）—— 与生产装配同型。
    app.state.web_gateway = Gateway(
        channels=None,
        identity=WebIdentityVerifier(),
        normalizers={ChannelType.WEB: WebChatNormalizer()},
        idempotency=IdempotencyGuard(InMemoryIdempotencyStore()),
        # 重放的落点（Stage 4b）—— 与 copilot 写事件用的是同一个日志。
        events=journal,
    )
    return app


@pytest.mark.asyncio
async def test_a_repeated_request_replays_the_previous_stream() -> None:
    """同一个 clientRequestId 再来一次 → **重放上一轮的事件流**（200）。"""
    agent = _agent()
    owner_id = UserId(UUID(int=3))
    svc, sid, tid, wid = await _make_service(agent, owner_id)

    app = _app(svc, svc._journal)
    headers = {
        "X-Tenant-Id": str(tid),
        "X-Workspace-Id": str(wid),
        "X-User-Id": str(owner_id),
    }
    with TestClient(app) as client:
        first = client.post(
            f"/api/sessions/{sid}/turns/stream",
            json={"content": "hi", "clientRequestId": "req-1"},
            headers=headers,
        )
        assert first.status_code == 200

        second = client.post(
            f"/api/sessions/{sid}/turns/stream",
            json={"content": "hi", "clientRequestId": "req-1"},
            headers=headers,
        )
        # ⚠️ **不再是 202** —— 重放就是重放（§10 Stage 4b 的验收）。
        assert second.status_code == 200
        assert second.headers["content-type"].startswith("text/event-stream")
        # 重放的内容与原始流一致。
        assert _chunk_payloads(second.text) == _chunk_payloads(first.text)


@pytest.mark.asyncio
async def test_a_repeated_request_does_not_run_the_turn_again() -> None:
    """重复请求**不得**再跑一轮 —— 重放的是事件，不是重算。"""
    agent = _agent()
    owner_id = UserId(UUID(int=3))
    svc, sid, tid, wid = await _make_service(agent, owner_id)
    llm = _LLM()
    svc._graph._llm = llm

    app = _app(svc, svc._journal)
    headers = {
        "X-Tenant-Id": str(tid),
        "X-Workspace-Id": str(wid),
        "X-User-Id": str(owner_id),
    }
    with TestClient(app) as client:
        for _ in range(3):
            response = client.post(
                f"/api/sessions/{sid}/turns/stream",
                json={"content": "hi", "clientRequestId": "req-1"},
                headers=headers,
            )
            assert response.status_code == 200
    # 模型只被调用了一轮。
    assert len(llm.requests) == 1


@pytest.mark.asyncio
async def test_the_replayed_events_have_the_same_digest_as_the_original() -> None:
    """**重放一致性校验**：重放流的摘要 == 原流 chunk 序列的摘要。"""
    agent = _agent()
    owner_id = UserId(UUID(int=3))
    svc, sid, tid, wid = await _make_service(agent, owner_id)

    app = _app(svc, svc._journal)
    headers = {
        "X-Tenant-Id": str(tid),
        "X-Workspace-Id": str(wid),
        "X-User-Id": str(owner_id),
    }
    with TestClient(app) as client:
        first = client.post(
            f"/api/sessions/{sid}/turns/stream",
            json={"content": "hi", "clientRequestId": "req-1"},
            headers=headers,
        )
        assert first.status_code == 200
        second = client.post(
            f"/api/sessions/{sid}/turns/stream",
            json={"content": "hi", "clientRequestId": "req-1"},
            headers=headers,
        )
        assert second.status_code == 200

    original = _events(first.text)
    replayed = _events(second.text)
    assert event_digest(replayed) == event_digest(original)
    # seq 连续 —— 1, 2, 3 …（客户端靠它续传）。
    assert [event.seq for event in replayed] == list(
        range(1, len(replayed) + 1)
    )


@pytest.mark.asyncio
async def test_the_last_event_id_resumes_from_that_point() -> None:
    """带 ``Last-Event-ID`` 重连 → **只重放它之后**的那几段。"""
    agent = _agent()
    owner_id = UserId(UUID(int=3))
    svc, sid, tid, wid = await _make_service(agent, owner_id)

    app = _app(svc, svc._journal)
    headers = {
        "X-Tenant-Id": str(tid),
        "X-Workspace-Id": str(wid),
        "X-User-Id": str(owner_id),
    }
    with TestClient(app) as client:
        first = client.post(
            f"/api/sessions/{sid}/turns/stream",
            json={"content": "hi", "clientRequestId": "req-1"},
            headers=headers,
        )
        assert first.status_code == 200
        total = len(_chunk_payloads(first.text))

        resumed = client.post(
            f"/api/sessions/{sid}/turns/stream",
            json={"content": "hi", "clientRequestId": "req-1"},
            headers={**headers, "Last-Event-ID": "1"},
        )
        assert resumed.status_code == 200
        payloads = _chunk_payloads(resumed.text)
        # 只剩第 2 段之后的内容。
        assert len(payloads) == total - 1
        assert payloads[0]["seq"] == 2


@pytest.mark.asyncio
async def test_a_duplicate_without_replayable_events_is_a_conflict() -> None:
    """重放不了（这一轮还没落过事件）→ **409**，不是 202、也不是静默丢弃。"""
    agent = _agent()
    owner_id = UserId(UUID(int=3))
    svc, sid, tid, wid = await _make_service(agent, owner_id)

    # ⚠️ 门面挂一个**空的**日志 —— 模拟「事件还没落库 / 这一轮还在跑」。
    app = _app(svc, InMemorySessionJournal())
    headers = {
        "X-Tenant-Id": str(tid),
        "X-Workspace-Id": str(wid),
        "X-User-Id": str(owner_id),
    }
    with TestClient(app) as client:
        first = client.post(
            f"/api/sessions/{sid}/turns/stream",
            json={"content": "hi", "clientRequestId": "req-1"},
            headers=headers,
        )
        assert first.status_code == 200
        second = client.post(
            f"/api/sessions/{sid}/turns/stream",
            json={"content": "hi", "clientRequestId": "req-1"},
            headers=headers,
        )
        assert second.status_code == 409
        body = second.json()
        assert body["code"] == "DUPLICATE_REQUEST"
        assert body["replayUnavailable"] is True
