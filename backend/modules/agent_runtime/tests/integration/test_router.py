"""HTTP integration tests for the agent_runtime router.

Wires the router onto a minimal FastAPI app with **no** middleware chain and
overrides `agent_runtime_dependency` so the route handlers run against the
in-memory ports from `../unit/_in_memory.py`. This exercises the real
`build_router()` code (request validation, response shaping, the
`safe_stream()` pre-flight error capture) without spinning up a Postgres
container or going through the JWT auth middleware.

Coverage matrix (Week 2 §P1 exit criteria):
  POST   /v1/agents/{aid}/sessions            201, 422
  GET    /v1/sessions/{sid}                   200, 404
  POST   /v1/sessions/{sid}/close             204, 404
  POST   /v1/sessions/{sid}/turn/stream       200 (SSE), 404, 410
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import pytest
from _ar_unit_in_memory import (
    FakeLLM,
    InMemorySessionRepository,
    InMemoryTurnRepository,
    RecordingEventPublisher,
)
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from qzdap.modules.agent_runtime.adapter.http.router import (
    agent_runtime_dependency,
    build_router,
)
from qzdap.modules.agent_runtime.application.services import AgentRuntimeService

# ── App + dependency override ──────────────────────────────────────────────


def _build_test_app(
    *,
    llm_content: str = "echo",
    raise_on_first_chunk: Exception | None = None,
) -> tuple[FastAPI, dict]:
    """Build a minimal FastAPI app with the agent_runtime router.

    Returns `(app, ctx)` where `ctx` exposes the in-memory repos + event
    publisher so tests can seed state and assert side-effects.
    """
    sessions = InMemorySessionRepository()
    turns = InMemoryTurnRepository()
    llm = FakeLLM(
        content=llm_content,
        raise_on_first_chunk=raise_on_first_chunk,
    )
    events = RecordingEventPublisher()
    svc = AgentRuntimeService(
        sessions=sessions,
        turns=turns,
        llm=llm,
        events=events,
    )

    app = FastAPI(title="agent_runtime-test")
    # Translate AppError subclasses → proper HTTP envelopes with the right
    # status code (mirrors what `qzdap_http.middleware.build_default_middleware_chain`
    # does in production).
    from qzdap_http.error_envelope import error_envelope_middleware
    from starlette.middleware.base import BaseHTTPMiddleware

    app.add_middleware(BaseHTTPMiddleware, dispatch=error_envelope_middleware)  # type: ignore[arg-type]
    app.include_router(build_router())

    # run_turn_stream reads `app.state.settings.llm_default_model`.
    from types import SimpleNamespace

    app.state.settings = SimpleNamespace(llm_default_model="mock-model")

    async def _provide_svc() -> AsyncIterator[AgentRuntimeService]:
        yield svc

    app.dependency_overrides[agent_runtime_dependency] = _provide_svc
    return app, {
        "sessions": sessions,
        "turns": turns,
        "llm": llm,
        "events": events,
        "svc": svc,
    }


def _make_client(app: FastAPI) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")


# ── Constants used by the tests ────────────────────────────────────────────

TENANT = UUID("00000000-0000-0000-0000-000000000001")
OTHER_TENANT = UUID("00000000-0000-0000-0000-000000000fff")
WORKSPACE = UUID("00000000-0000-0000-0000-000000000002")
AGENT = UUID("00000000-0000-0000-0000-000000000099")
USER = UUID("00000000-0000-0000-0000-000000000010")


def _hdrs(tenant: UUID = TENANT, workspace: UUID = WORKSPACE) -> dict[str, str]:
    return {
        "X-Tenant-Id": str(tenant),
        "X-Workspace-Id": str(workspace),
    }


async def _seed_session(ctx: dict, *, closed: bool = False) -> UUID:
    """Seed a session via the service so the HTTP layer only sees an id."""
    s = (
        await ctx["svc"]
        .create_session()
        .execute(
            tenant_id=TENANT,
            workspace_id=WORKSPACE,
            owner_id=USER,
            agent_id=AGENT,
            agent_version="1.0.0",
        )
    )
    if closed:
        await ctx["svc"].close_session().execute(tenant_id=TENANT, session_id=s.id)
    return s.id


# ── POST /v1/agents/{aid}/sessions ────────────────────────────────────────


async def test_create_session_returns_201_with_location() -> None:
    app, _ctx = _build_test_app()

    async with _make_client(app) as client:
        resp = await client.post(
            f"/v1/agents/{AGENT}/sessions",
            json={"agent_version": "1.0.0", "metadata": {"k": "v"}},
            headers=_hdrs(),
        )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["agent_id"] == str(AGENT)
    assert body["status"] == "open"
    assert body["agent_version"] == "1.0.0"
    # Location header must point at the GET endpoint.
    loc = resp.headers["Location"]
    assert loc.startswith("/v1/sessions/")
    assert UUID(loc.rsplit("/", 1)[-1]) == UUID(body["id"])


async def test_create_session_validates_agent_version() -> None:
    app, _ctx = _build_test_app()

    async with _make_client(app) as client:
        resp = await client.post(
            f"/v1/agents/{AGENT}/sessions",
            json={"agent_version": ""},
            headers=_hdrs(),
        )

    # Pydantic validation → 422 from FastAPI.
    assert resp.status_code == 422
    assert "agent_version" in resp.text


async def test_create_session_requires_tenant_header() -> None:
    app, _ctx = _build_test_app()

    async with _make_client(app) as client:
        resp = await client.post(
            f"/v1/agents/{AGENT}/sessions",
            json={"agent_version": "1.0.0"},
            # No X-Tenant-Id / X-Workspace-Id.
        )

    assert resp.status_code == 422
    assert "X-Tenant-Id" in resp.text or "tenant" in resp.text.lower()


async def test_create_session_requires_workspace_header() -> None:
    app, _ctx = _build_test_app()

    async with _make_client(app) as client:
        resp = await client.post(
            f"/v1/agents/{AGENT}/sessions",
            json={"agent_version": "1.0.0"},
            headers={"X-Tenant-Id": str(TENANT)},
        )

    assert resp.status_code == 422


async def test_create_session_rejects_malformed_uuid() -> None:
    app, _ctx = _build_test_app()

    async with _make_client(app) as client:
        resp = await client.post(
            "/v1/agents/not-a-uuid/sessions",
            json={"agent_version": "1.0.0"},
            headers=_hdrs(),
        )

    assert resp.status_code == 422


# ── GET /v1/sessions/{sid} ────────────────────────────────────────────────


async def test_get_session_returns_session() -> None:
    app, ctx = _build_test_app()
    sid = await _seed_session(ctx)

    async with _make_client(app) as client:
        resp = await client.get(f"/v1/sessions/{sid}", headers=_hdrs())

    assert resp.status_code == 200, resp.text
    assert resp.json()["id"] == str(sid)
    assert resp.json()["status"] == "open"


async def test_get_session_returns_404_when_unknown() -> None:
    app, _ctx = _build_test_app()

    async with _make_client(app) as client:
        resp = await client.get(f"/v1/sessions/{uuid4()}", headers=_hdrs())

    assert resp.status_code == 404, resp.text
    body = resp.json()
    assert body["code"] == "SESSION_NOT_FOUND"
    assert body["status"] == 404
    assert body["title"] == "SESSION_NOT_FOUND"


async def test_get_session_returns_404_when_cross_tenant() -> None:
    app, ctx = _build_test_app()
    sid = await _seed_session(ctx)

    async with _make_client(app) as client:
        resp = await client.get(
            f"/v1/sessions/{sid}", headers=_hdrs(tenant=OTHER_TENANT)
        )

    # Cross-tenant access must NOT return the session.
    assert resp.status_code == 404, resp.text
    assert resp.json()["code"] == "SESSION_NOT_FOUND"


# ── POST /v1/sessions/{sid}/close ─────────────────────────────────────────


async def test_close_session_returns_204() -> None:
    app, ctx = _build_test_app()
    sid = await _seed_session(ctx)

    async with _make_client(app) as client:
        resp = await client.post(f"/v1/sessions/{sid}/close", headers=_hdrs())

    assert resp.status_code == 204
    assert resp.content == b""


async def test_close_session_returns_404_when_unknown() -> None:
    app, _ctx = _build_test_app()

    async with _make_client(app) as client:
        resp = await client.post(f"/v1/sessions/{uuid4()}/close", headers=_hdrs())

    assert resp.status_code == 404, resp.text


# ── POST /v1/sessions/{sid}/turn/stream ───────────────────────────────────


async def test_run_turn_stream_emits_sse_chunks() -> None:
    app, ctx = _build_test_app(llm_content="hi")
    sid = await _seed_session(ctx)

    async with (
        _make_client(app) as client,
        client.stream(
            "POST",
            f"/v1/sessions/{sid}/turn/stream",
            json={"content": "hello"},
            headers=_hdrs(),
        ) as resp,
    ):
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        body = b""
        async for chunk in resp.aiter_bytes():
            body += chunk

    # The FakeLLM emits one message chunk + one final stop chunk → SSE frames.
    text = body.decode("utf-8")
    assert "event: message" in text
    assert '"content":"hi"' in text
    assert "event: done" in text
    assert "event: end" in text

    # The use case must have persisted the running → succeeded turn.
    assert len(ctx["turns"]._by_id) == 1
    persisted = next(iter(ctx["turns"]._by_id.values()))
    assert persisted.status.value == "succeeded"


async def test_run_turn_stream_returns_404_when_unknown_session() -> None:
    app, _ctx = _build_test_app()

    async with _make_client(app) as client:
        resp = await client.post(
            f"/v1/sessions/{uuid4()}/turn/stream",
            json={"content": "hi"},
            headers=_hdrs(),
        )

    # Pre-flight error capture in run_turn_stream() must surface the
    # SessionNotFound as a proper HTTP error envelope, not a torn SSE.
    assert resp.status_code == 404, resp.text
    body = resp.json()
    assert body["code"] == "SESSION_NOT_FOUND"
    # Critically: the body must NOT contain partial SSE framing.
    assert "event: message" not in resp.text


async def test_run_turn_stream_returns_410_when_session_closed() -> None:
    app, ctx = _build_test_app(llm_content="hi")
    sid = await _seed_session(ctx, closed=True)

    async with _make_client(app) as client:
        resp = await client.post(
            f"/v1/sessions/{sid}/turn/stream",
            json={"content": "hi"},
            headers=_hdrs(),
        )

    # SessionClosedError must surface as a proper HTTP error envelope,
    # not a partial SSE stream.
    assert resp.status_code == 410, resp.text
    assert resp.json()["code"] == "SESSION_CLOSED"
    assert "event: message" not in resp.text


@pytest.mark.parametrize("llm_content", ["latency", "你好"])
async def test_run_turn_stream_first_chunk_latency_below_one_second(
    llm_content: str,
) -> None:
    """Week 2 §P1 exit criterion: first SSE chunk ≤ 1000 ms."""
    import time

    app, ctx = _build_test_app(llm_content=llm_content)
    sid = await _seed_session(ctx)

    async with _make_client(app) as client:
        t0 = time.perf_counter()
        async with client.stream(
            "POST",
            f"/v1/sessions/{sid}/turn/stream",
            json={"content": "ping"},
            headers=_hdrs(),
        ) as resp:
            assert resp.status_code == 200
            first_chunk = await resp.aiter_bytes().__anext__()
            first_ms = (time.perf_counter() - t0) * 1000

    assert first_chunk, "stream must produce at least one byte"
    assert first_ms < 1000, f"first chunk took {first_ms:.1f}ms"


async def test_run_turn_stream_validates_request_body() -> None:
    app, ctx = _build_test_app()
    sid = await _seed_session(ctx)

    async with _make_client(app) as client:
        resp = await client.post(
            f"/v1/sessions/{sid}/turn/stream",
            json={"content": ""},
            headers=_hdrs(),
        )

    # Empty content → Pydantic 422.
    assert resp.status_code == 422
