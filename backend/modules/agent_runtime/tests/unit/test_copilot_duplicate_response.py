"""重复请求的**降级路径** —— 202 + turn_id + replay_unavailable（Gateway §4.5）。

命中重复时，正确行为是「重放上一轮事件流」；``session_events`` 真写真读就绪之前
（Gateway Stage 4b），降级为「**202 + 上次 turn_id + replay_unavailable**」。

**不得静默丢弃重复请求** —— 客户端必须知道「这一轮到底跑没跑」。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID

import pytest
from _ar_unit_in_memory import InMemoryIdempotencyStore, make_dependencies
from fastapi import FastAPI
from fastapi.testclient import TestClient
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
    )
    tid = TenantId(agent.tenant_id)
    wid = WorkspaceId(agent.workspace_id)
    detail = await svc.create_session(
        tenant_id=tid, workspace_id=wid, owner_id=owner_id, agent_id=agent.id
    )
    return svc, detail["id"], tid, wid


@pytest.mark.asyncio
async def test_a_repeated_request_answers_202_with_the_previous_turn_id() -> None:
    """同一个 clientRequestId 再来一次 → **202 + 上次 turn_id**，不是错误。"""
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
        assert second.status_code == 202
        body = second.json()
        assert body["code"] == "DUPLICATE_REQUEST"
        assert body["replayUnavailable"] is True
        # 上一次那一轮的 turn_id —— 客户端据此知道「跑过了，是哪一轮」。
        assert body["turnId"]
