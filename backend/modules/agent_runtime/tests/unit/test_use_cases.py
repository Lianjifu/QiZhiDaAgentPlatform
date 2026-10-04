"""Use case tests for the agent runtime (in-memory adapters, no DB)."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from _ar_unit_in_memory import make_dependencies
from qzdap_schema.ids import (
    AgentId,
    TenantId,
    UserId,
    WorkspaceId,
)

from qzdap.modules.agent_runtime.application.services import AgentRuntimeService
from qzdap.modules.agent_runtime.domain import (
    SessionStatus,
    TurnStatus,
)
from qzdap.modules.agent_runtime.domain.errors import (
    SessionClosedError,
    SessionNotFound,
)


def _make_owners() -> tuple[TenantId, WorkspaceId, UserId, AgentId]:
    return (
        TenantId(uuid4()),
        WorkspaceId(uuid4()),
        UserId(uuid4()),
        AgentId(uuid4()),
    )


@pytest.mark.asyncio
async def test_create_session_persists_and_emits_event() -> None:
    deps = make_dependencies()
    svc = AgentRuntimeService(**deps)
    tid, wid, uid, aid = _make_owners()

    s = await svc.create_session().execute(
        tenant_id=tid,
        workspace_id=wid,
        owner_id=uid,
        agent_id=aid,
        agent_version="1.0.0",
        metadata={"source": "unit-test"},
    )
    assert s.status is SessionStatus.OPEN
    assert s.agent_version == "1.0.0"
    assert s.metadata["source"] == "unit-test"

    fetched = await deps["sessions"].get(s.id)
    assert fetched == s

    event_types = [type(e).__name__ for e in deps["events"].events]
    assert "SessionOpened" in event_types


@pytest.mark.asyncio
async def test_close_session_marks_closed_and_emits_event() -> None:
    deps = make_dependencies()
    svc = AgentRuntimeService(**deps)
    tid, wid, uid, aid = _make_owners()
    s = await svc.create_session().execute(
        tenant_id=tid,
        workspace_id=wid,
        owner_id=uid,
        agent_id=aid,
        agent_version="1.0.0",
    )

    await svc.close_session().execute(tenant_id=tid, session_id=s.id)
    closed = await deps["sessions"].get(s.id)
    assert closed is not None and closed.status is SessionStatus.CLOSED

    event_types = [type(e).__name__ for e in deps["events"].events]
    assert "SessionClosed" in event_types


@pytest.mark.asyncio
async def test_close_session_is_idempotent_for_use_case() -> None:
    """The use case silently no-ops on a second close (so chatty retries
    don't 500); the domain aggregate itself still raises for audit hygiene."""
    deps = make_dependencies()
    svc = AgentRuntimeService(**deps)
    tid, wid, uid, aid = _make_owners()
    s = await svc.create_session().execute(
        tenant_id=tid,
        workspace_id=wid,
        owner_id=uid,
        agent_id=aid,
        agent_version="1.0.0",
    )
    await svc.close_session().execute(tenant_id=tid, session_id=s.id)
    # Second close: no exception, no extra event.
    await svc.close_session().execute(tenant_id=tid, session_id=s.id)
    closed_events = [
        e for e in deps["events"].events if type(e).__name__ == "SessionClosed"
    ]
    assert len(closed_events) == 1


@pytest.mark.asyncio
async def test_get_session_returns_not_found_for_other_tenant() -> None:
    deps = make_dependencies()
    svc = AgentRuntimeService(**deps)
    tid, wid, uid, aid = _make_owners()
    s = await svc.create_session().execute(
        tenant_id=tid,
        workspace_id=wid,
        owner_id=uid,
        agent_id=aid,
        agent_version="1.0.0",
    )
    other_tenant = TenantId(uuid4())
    with pytest.raises(SessionNotFound):
        await svc.get_session().execute(tenant_id=other_tenant, session_id=s.id)


@pytest.mark.asyncio
async def test_run_turn_streams_message_done_and_emits_completed() -> None:
    deps = make_dependencies(llm_content="hi")
    svc = AgentRuntimeService(**deps)
    tid, wid, uid, aid = _make_owners()
    s = await svc.create_session().execute(
        tenant_id=tid,
        workspace_id=wid,
        owner_id=uid,
        agent_id=aid,
        agent_version="1.0.0",
    )

    chunks: list = []
    async for c in svc.run_turn().execute(
        tenant_id=tid,
        workspace_id=wid,
        owner_id=uid,
        session_id=s.id,
        user_input="hello",
        model="gpt-4o-mini",
    ):
        chunks.append(c)

    kinds = [c.kind for c in chunks]
    assert "message" in kinds
    assert "done" in kinds
    done = next(c for c in chunks if c.kind == "done")
    assert done.final_message == "hi"

    event_types = [type(e).__name__ for e in deps["events"].events]
    assert "TurnStarted" in event_types
    assert "TurnCompleted" in event_types

    persisted = [t for t in deps["turns"]._by_id.values()]
    assert persisted and persisted[0].status is TurnStatus.SUCCEEDED
    assert persisted[0].final_response == "hi"


@pytest.mark.asyncio
async def test_run_turn_emits_tool_call_chunks_but_does_not_invoke_tools() -> None:
    deps = make_dependencies(
        llm_content="ok",
        tool_calls=[
            {
                "id": "00000000-0000-0000-0000-000000000001",
                "function": {
                    "name": "lookup_workspace",
                    "arguments": '{"workspace_id":"ws-1"}',
                },
            }
        ],
    )
    svc = AgentRuntimeService(**deps)
    tid, wid, uid, aid = _make_owners()
    s = await svc.create_session().execute(
        tenant_id=tid,
        workspace_id=wid,
        owner_id=uid,
        agent_id=aid,
        agent_version="1.0.0",
    )

    chunks = []
    async for c in svc.run_turn().execute(
        tenant_id=tid,
        workspace_id=wid,
        owner_id=uid,
        session_id=s.id,
        user_input="do something",
        model="gpt-4o-mini",
    ):
        chunks.append(c)
    tool_chunks = [c for c in chunks if c.kind == "tool_call"]
    assert len(tool_chunks) == 1
    assert tool_chunks[0].tool_name == "lookup_workspace"
    assert tool_chunks[0].arguments == {"workspace_id": "ws-1"}
    # No ToolPort wired → no ToolResultChunk emitted.
    assert not any(c.kind == "tool_result" for c in chunks)


@pytest.mark.asyncio
async def test_run_turn_invokes_tool_port_when_wired() -> None:
    from uuid import UUID

    deps = make_dependencies(
        llm_content="ok",
        tool_calls=[
            {
                "id": "00000000-0000-0000-0000-0000000000aa",
                "function": {
                    "name": "echo",
                    "arguments": '{"hi":"there"}',
                },
            }
        ],
    )
    svc = AgentRuntimeService(**deps)

    class _EchoToolPort:
        async def invoke(self, *, call_id, tool_name, arguments):  # type: ignore[no-untyped-def]
            return {"echoed": arguments}

    svc.tool_port = _EchoToolPort()
    tid, wid, uid, aid = _make_owners()
    s = await svc.create_session().execute(
        tenant_id=tid,
        workspace_id=wid,
        owner_id=uid,
        agent_id=aid,
        agent_version="1.0.0",
    )

    chunks = []
    async for c in svc.run_turn().execute(
        tenant_id=tid,
        workspace_id=wid,
        owner_id=uid,
        session_id=s.id,
        user_input="do something",
        model="gpt-4o-mini",
    ):
        chunks.append(c)

    tool_result = next(c for c in chunks if c.kind == "tool_result")
    assert tool_result.tool_call_id == UUID("00000000-0000-0000-0000-0000000000aa")
    assert tool_result.output == {"echoed": {"hi": "there"}}
    assert tool_result.is_error is False
    assert tool_result.latency_ms >= 0


@pytest.mark.asyncio
async def test_run_turn_routes_sandbox_exec_and_catalog_skill() -> None:
    from uuid import UUID

    deps = make_dependencies(
        llm_content="ok",
        tool_calls=[
            {
                "id": "00000000-0000-0000-0000-0000000000bb",
                "function": {
                    "name": "sandbox_exec",
                    "arguments": '{"language":"python","code":"print(1)"}',
                },
            },
            {
                "id": "00000000-0000-0000-0000-0000000000cc",
                "function": {
                    "name": "周报助手",
                    "arguments": "{}",
                },
            },
        ],
    )
    svc = AgentRuntimeService(**deps)

    class _Sandbox:
        async def exec(self, *, call_id, language, code, timeout_ms=30000):  # type: ignore[no-untyped-def]
            return {"ok": True, "stdout": "1", "language": language, "code": code}

    class _Skills:
        async def list_executable(self):  # type: ignore[no-untyped-def]
            return [{"name": "周报助手", "description": "x", "inputSchema": []}]

        async def invoke(self, *, call_id, skill_name, arguments):  # type: ignore[no-untyped-def]
            return {"ok": True, "name": skill_name, "arguments": arguments}

    svc.sandbox_port = _Sandbox()
    svc.skill_port = _Skills()
    tid, wid, uid, aid = _make_owners()
    s = await svc.create_session().execute(
        tenant_id=tid,
        workspace_id=wid,
        owner_id=uid,
        agent_id=aid,
        agent_version="1.0.0",
    )
    chunks = []
    async for c in svc.run_turn().execute(
        tenant_id=tid,
        workspace_id=wid,
        owner_id=uid,
        session_id=s.id,
        user_input="run",
        model="gpt-4o-mini",
    ):
        chunks.append(c)
    results = [c for c in chunks if c.kind == "tool_result"]
    assert results[0].output["stdout"] == "1"
    assert results[1].output["name"] == "周报助手"
    _ = UUID


@pytest.mark.asyncio
async def test_run_turn_on_closed_session_raises() -> None:
    deps = make_dependencies()
    svc = AgentRuntimeService(**deps)
    tid, wid, uid, aid = _make_owners()
    s = await svc.create_session().execute(
        tenant_id=tid,
        workspace_id=wid,
        owner_id=uid,
        agent_id=aid,
        agent_version="1.0.0",
    )
    await svc.close_session().execute(tenant_id=tid, session_id=s.id)

    with pytest.raises(SessionClosedError):
        async for _ in svc.run_turn().execute(
            tenant_id=tid,
            workspace_id=wid,
            owner_id=uid,
            session_id=s.id,
            user_input="x",
            model="gpt-4o-mini",
        ):
            pass


@pytest.mark.asyncio
async def test_run_turn_unknown_session_raises_not_found() -> None:
    deps = make_dependencies()
    svc = AgentRuntimeService(**deps)
    tid, wid, uid, _aid = _make_owners()
    with pytest.raises(SessionNotFound):
        async for _ in svc.run_turn().execute(
            tenant_id=tid,
            workspace_id=wid,
            owner_id=uid,
            session_id=UUID("00000000-0000-0000-0000-0000000000ff"),
            user_input="x",
            model="gpt-4o-mini",
        ):
            pass


@pytest.mark.asyncio
async def test_run_turn_first_chunk_yields_within_first_message() -> None:
    """SLA: first chunk arrives immediately (synchronous fake LLM)."""
    deps = make_dependencies(llm_content="fast")
    svc = AgentRuntimeService(**deps)
    tid, wid, uid, aid = _make_owners()
    s = await svc.create_session().execute(
        tenant_id=tid,
        workspace_id=wid,
        owner_id=uid,
        agent_id=aid,
        agent_version="1.0.0",
    )
    it = svc.run_turn().execute(
        tenant_id=tid,
        workspace_id=wid,
        owner_id=uid,
        session_id=s.id,
        user_input="x",
        model="gpt-4o-mini",
    )
    first = await it.__anext__()
    assert first.kind == "message"
    assert first.content == "fast"
    # drain
    async for _ in it:
        pass
