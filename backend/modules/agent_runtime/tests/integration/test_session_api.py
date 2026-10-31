"""HTTP 集成测试 —— 会话 API 的**唯一入口** ``/api/sessions*``。

⚠️ 旧的 ``/v1/sessions*`` 路由已删除（Gateway Stage 5，台账 **G7 / G8**）——
API owner 已确认无仓外调用方（方案 §9.4 的前置 **P-11**）→ 兼容保留期归零。

本文件承接原 ``test_router.py`` 的覆盖（**契约不随路由搬家而丢失**）：

  POST   /api/sessions                  201, 400, 422
  GET    /api/sessions/{sid}            200, 404
  DELETE /api/sessions/{sid}            204, 404
  POST   /api/sessions/{sid}/turns/stream   200 (SSE), 400, 404
"""

from __future__ import annotations

import time
from uuid import UUID, uuid4

import pytest
from _ar_unit_in_memory import (
    FakeLLM,
    InMemoryIdempotencyStore,
    InMemorySessionJournal,
    InMemorySessionRepository,
    InMemoryTurnClaim,
    InMemoryTurnRepository,
    RecordingEventPublisher,
    make_turn_runner,
)
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from qzdap.modules.agent_runtime.adapter.graph.runner import SessionGraphRunner
from qzdap.modules.agent_runtime.application.copilot import CopilotSessionService
from qzdap.modules.agent_runtime.domain.catalog import CatalogAgent
from qzdap_agent_runtime.gateway.facade import Gateway
from qzdap_agent_runtime.gateway.idempotency import IdempotencyGuard
from qzdap_agent_runtime.gateway.types import ChannelType
from qzdap_agent_runtime.gateway.web import WebChatNormalizer, WebIdentityVerifier
from qzdap_kernel.ids import AgentId, TenantId, WorkspaceId

# ── App + dependency override ──────────────────────────────────────────────

TENANT = UUID("00000000-0000-0000-0000-000000000001")
OTHER_TENANT = UUID("00000000-0000-0000-0000-000000000fff")
WORKSPACE = UUID("00000000-0000-0000-0000-000000000002")
AGENT = UUID("00000000-0000-0000-0000-000000000099")
OWNER = UUID("00000000-0000-0000-0000-000000000010")


class _Catalog:
    def __init__(self, agent: CatalogAgent) -> None:
        self._agent = agent

    async def get_published(self, agent_id):  # type: ignore[no-untyped-def]
        return self._agent

    async def get_admin(self, agent_id):  # type: ignore[no-untyped-def]
        return self._agent.to_admin_dict()

    async def list_admin(self, *, workspace_id):  # type: ignore[no-untyped-def]
        """候选池 —— 真实实现走 ``to_admin_dict``，这里给同样的形状。"""
        row = self._agent.to_admin_dict()
        row["status"] = "published"
        return [row]


class _Messages:
    def __init__(self) -> None:
        self.rows: list[dict] = []

    async def list_for_session(self, session_id):  # type: ignore[no-untyped-def]
        return self.rows

    async def append(self, **kwargs):  # type: ignore[no-untyped-def]
        self.rows.append(kwargs)

    async def next_seq(self, *, session_id):  # type: ignore[no-untyped-def]
        """下一个轮次内序号 ✓（与真实实现同语义）。"""
        return (self.rows[-1]["seq"] + 1) if self.rows else 0


def _agent() -> CatalogAgent:
    return CatalogAgent.create(
        id=AgentId(AGENT),
        tenant_id=TenantId(TENANT),
        workspace_id=WorkspaceId(WORKSPACE),
        name="t",
        category="test",
        owner="test",
        model="default",
    )


def _build_test_app(
    *,
    llm_content: str = "echo",
    raise_on_first_chunk: Exception | None = None,
) -> tuple[FastAPI, dict]:
    """最小 FastAPI app —— 只挂 ``/api/sessions*``，端口全部走内存替身。"""
    from qzdap.modules.agent_runtime.adapter.http.session_router import (
        build_session_router,
        copilot_dependency,
        routing_strategy_dependency,
    )
    from qzdap.modules.agent_runtime.adapter.routing import CatalogRoutingAdapter
    from qzdap_agent_runtime.router.strategy import RuleChainStrategy

    sessions = InMemorySessionRepository()
    claim = InMemoryTurnClaim()
    llm = FakeLLM(content=llm_content, raise_on_first_chunk=raise_on_first_chunk)
    events = RecordingEventPublisher()
    journal = InMemorySessionJournal()
    # 轮次读仓库读**同一份行** ✓（停旧写后轮次只有一个落点 ✓）。
    turns = InMemoryTurnRepository(journal)
    catalog = _Catalog(_agent())
    messages = _Messages()
    runner = SessionGraphRunner(llm=llm)
    svc = CopilotSessionService(
        sessions=sessions,
        turns=turns,
        messages=messages,  # type: ignore[arg-type]
        catalog=catalog,  # type: ignore[arg-type]
        events=events,
        graph=runner,
        idempotency=IdempotencyGuard(InMemoryIdempotencyStore()),
        journal=journal,
        claim=claim,
        turn_runner=make_turn_runner(
            graph=runner,
            journal=journal,
            events=events,
            messages=messages,
            sessions=sessions,
        ),
    )
    # Router 的规则链（真实现，候选池来自同一个 catalog 替身）。
    strategy = RuleChainStrategy(catalog=CatalogRoutingAdapter(catalog))  # type: ignore[arg-type]

    app = FastAPI(title="agent_runtime-test")
    # AppError → HTTP 错误信封（与生产中间件链同源）。
    from starlette.middleware.base import BaseHTTPMiddleware

    from qzdap_http.error_envelope import error_envelope_middleware

    app.add_middleware(BaseHTTPMiddleware, dispatch=error_envelope_middleware)  # type: ignore[arg-type]
    app.include_router(build_session_router())
    app.dependency_overrides[copilot_dependency] = lambda: svc
    app.dependency_overrides[routing_strategy_dependency] = lambda: strategy
    # web 入口的门面（①②③ + ④）—— 与生产装配同型。
    app.state.web_gateway = Gateway(
        channels=None,
        identity=WebIdentityVerifier(),
        normalizers={ChannelType.WEB: WebChatNormalizer()},
        idempotency=IdempotencyGuard(InMemoryIdempotencyStore()),
        events=journal,
    )
    return app, {
        "sessions": sessions,
        "turns": turns,
        "llm": llm,
        "events": events,
        "journal": journal,
        "svc": svc,
    }


def _make_client(app: FastAPI) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")


def _hdrs(tenant: UUID = TENANT, workspace: UUID = WORKSPACE) -> dict[str, str]:
    return {
        "X-Tenant-Id": str(tenant),
        "X-Workspace-Id": str(workspace),
        "X-User-Id": str(OWNER),
    }


async def _seed_session(ctx: dict, *, closed: bool = False) -> UUID:
    detail = await ctx["svc"].create_session(
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        owner_id=OWNER,
        agent_id=AGENT,
    )
    session_id = UUID(detail["id"])
    if closed:
        await ctx["svc"].close_session(tenant_id=TENANT, session_id=session_id)
    return session_id


# ── POST /api/sessions ────────────────────────────────────────────────────


async def test_create_session_returns_201_with_the_detail_shape() -> None:
    app, _ctx = _build_test_app()

    async with _make_client(app) as client:
        resp = await client.post(
            "/api/sessions",
            json={"agentId": str(AGENT)},
            headers=_hdrs(),
        )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["id"]
    assert body["agentId"] == str(AGENT)
    assert body["status"] == "open"
    assert body["messages"] == []


async def test_create_session_requires_agent_id() -> None:
    app, _ctx = _build_test_app()

    async with _make_client(app) as client:
        resp = await client.post("/api/sessions", json={}, headers=_hdrs())

    assert resp.status_code == 400
    assert "agentId" in resp.text


async def test_create_session_records_the_route_decision() -> None:
    """路由决策必须留痕（Router §3.2）—— 挂在会话上，随轮次落库。"""
    app, ctx = _build_test_app()

    async with _make_client(app) as client:
        resp = await client.post("/api/sessions", json={"agentId": str(AGENT)}, headers=_hdrs())

    assert resp.status_code == 201, resp.text
    session_id = UUID(resp.json()["id"])
    session = await ctx["sessions"].get(session_id)
    assert session is not None
    decision = (session.metadata or {}).get("route_decision")
    assert decision is not None, "会话上必须带路由决策"
    assert decision["source"] == "explicit"
    assert decision["agent_id"] == str(AGENT)
    assert decision["strategy_id"] == "rule-chain"


async def test_the_route_decision_lands_in_the_turn_row() -> None:
    """``session_turns.route_decision`` —— 轮次行要能回答「为什么是这个 agent」。"""
    app, ctx = _build_test_app(llm_content="hi")

    async with _make_client(app) as client:
        resp = await client.post("/api/sessions", json={"agentId": str(AGENT)}, headers=_hdrs())
    session_id = UUID(resp.json()["id"])

    async with (
        _make_client(app) as client,
        client.stream(
            "POST",
            f"/api/sessions/{session_id}/turns/stream",
            json={"content": "hello"},
            headers=_hdrs(),
        ) as stream,
    ):
        assert stream.status_code == 200
        async for _chunk in stream.aiter_bytes():
            pass

    assert len(ctx["journal"].turns) == 1
    row = next(iter(ctx["journal"].turns.values()))
    assert row["route_decision"]["source"] == "explicit"
    assert row["route_decision"]["agent_id"] == str(AGENT)


async def test_create_session_requires_tenant_header() -> None:
    app, _ctx = _build_test_app()

    async with _make_client(app) as client:
        resp = await client.post("/api/sessions", json={"agentId": str(AGENT)})

    assert resp.status_code == 422
    assert "X-Tenant-Id" in resp.text or "tenant" in resp.text.lower()


async def test_create_session_requires_workspace_header() -> None:
    app, _ctx = _build_test_app()

    async with _make_client(app) as client:
        resp = await client.post(
            "/api/sessions",
            json={"agentId": str(AGENT)},
            headers={"X-Tenant-Id": str(TENANT)},
        )

    assert resp.status_code == 422


# ── GET /api/sessions/{sid} ───────────────────────────────────────────────


async def test_get_session_returns_session() -> None:
    app, ctx = _build_test_app()
    sid = await _seed_session(ctx)

    async with _make_client(app) as client:
        resp = await client.get(f"/api/sessions/{sid}", headers=_hdrs())

    assert resp.status_code == 200, resp.text
    assert resp.json()["id"] == str(sid)
    assert resp.json()["status"] == "open"


async def test_get_session_returns_404_when_unknown() -> None:
    app, _ctx = _build_test_app()

    async with _make_client(app) as client:
        resp = await client.get(f"/api/sessions/{uuid4()}", headers=_hdrs())

    assert resp.status_code == 404, resp.text
    assert resp.json()["code"] == "SESSION_NOT_FOUND"


async def test_get_session_returns_404_when_cross_tenant() -> None:
    app, ctx = _build_test_app()
    sid = await _seed_session(ctx)

    async with _make_client(app) as client:
        resp = await client.get(f"/api/sessions/{sid}", headers=_hdrs(tenant=OTHER_TENANT))

    # 跨租户访问**不得**返回会话。
    assert resp.status_code == 404, resp.text
    assert resp.json()["code"] == "SESSION_NOT_FOUND"


# ── DELETE /api/sessions/{sid} ────────────────────────────────────────────


async def test_delete_session_returns_204() -> None:
    app, ctx = _build_test_app()
    sid = await _seed_session(ctx)

    async with _make_client(app) as client:
        resp = await client.delete(f"/api/sessions/{sid}", headers=_hdrs())

    assert resp.status_code == 204
    assert resp.content == b""


async def test_delete_session_returns_404_when_unknown() -> None:
    app, _ctx = _build_test_app()

    async with _make_client(app) as client:
        resp = await client.delete(f"/api/sessions/{uuid4()}", headers=_hdrs())

    assert resp.status_code == 404, resp.text


# ── POST /api/sessions/{sid}/turns/stream ─────────────────────────────────


async def test_run_turn_stream_emits_sse_chunks() -> None:
    app, ctx = _build_test_app(llm_content="hi")
    sid = await _seed_session(ctx)

    async with (
        _make_client(app) as client,
        client.stream(
            "POST",
            f"/api/sessions/{sid}/turns/stream",
            json={"content": "hello"},
            headers=_hdrs(),
        ) as resp,
    ):
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        body = b""
        async for chunk in resp.aiter_bytes():
            body += chunk

    text = body.decode("utf-8")
    assert "event: message" in text
    assert '"content":"hi"' in text
    assert "event: done" in text
    assert "event: end" in text

    # 轮次必须落库（running → succeeded）。
    assert len(ctx["journal"].turns) == 1
    persisted = next(iter(ctx["journal"].turns.values()))
    assert persisted["status"] == "succeeded"
    # 事件流也必须落库（Gateway Stage 4b 的重放落点）。
    assert len(ctx["journal"].events) == 1


async def test_run_turn_stream_returns_404_when_unknown_session() -> None:
    app, _ctx = _build_test_app()

    async with _make_client(app) as client:
        resp = await client.post(
            f"/api/sessions/{uuid4()}/turns/stream",
            json={"content": "hi"},
            headers=_hdrs(),
        )

    # 首 chunk 预取必须把「会话不存在」变成正常的 HTTP 错误信封，
    # 而不是一段撕裂的 SSE。
    assert resp.status_code == 404, resp.text
    assert resp.json()["code"] == "SESSION_NOT_FOUND"
    assert "event: message" not in resp.text


async def test_run_turn_stream_rejects_empty_content() -> None:
    app, ctx = _build_test_app()
    sid = await _seed_session(ctx)

    async with _make_client(app) as client:
        resp = await client.post(
            f"/api/sessions/{sid}/turns/stream",
            json={"content": "  "},
            headers=_hdrs(),
        )

    assert resp.status_code == 400
    assert "content" in resp.text


@pytest.mark.parametrize("llm_content", ["latency", "你好"])
async def test_run_turn_stream_first_chunk_latency_below_one_second(
    llm_content: str,
) -> None:
    """首 chunk ≤ 1000 ms。"""
    app, ctx = _build_test_app(llm_content=llm_content)
    sid = await _seed_session(ctx)

    async with _make_client(app) as client:
        t0 = time.perf_counter()
        async with client.stream(
            "POST",
            f"/api/sessions/{sid}/turns/stream",
            json={"content": "ping"},
            headers=_hdrs(),
        ) as resp:
            assert resp.status_code == 200
            first_chunk = await resp.aiter_bytes().__anext__()
            first_ms = (time.perf_counter() - t0) * 1000

    assert first_chunk, "stream must produce at least one byte"
    assert first_ms < 1000, f"first chunk took {first_ms:.1f}ms"
