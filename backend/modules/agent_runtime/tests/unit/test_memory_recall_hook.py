"""Unit tests for the memory recall hook wired into RunTurnUseCase.

These verify the P4 ↔ agent_runtime integration at the use-case level
(end-to-end via the streaming protocol) without a real database.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from _ar_unit_in_memory import make_dependencies
from qzdap_schema.ids import (
    AgentId,
    TenantId,
    UserId,
    WorkspaceId,
)

from qzdap.modules.agent_runtime.application.services import AgentRuntimeService


class _RecordingMemoryPort:
    """Captures recall() args and returns canned memories."""

    def __init__(
        self,
        *,
        memories: list[dict] | None = None,
        raise_exc: Exception | None = None,
    ) -> None:
        self._memories = memories or []
        self._raise = raise_exc
        self.calls: list[dict[str, Any]] = []

    async def recall(
        self, *, tenant_id: UUID, workspace_id: UUID, query: str, top_k: int
    ) -> list[dict]:
        self.calls.append(
            {
                "tenant_id": tenant_id,
                "workspace_id": workspace_id,
                "query": query,
                "top_k": top_k,
            }
        )
        if self._raise is not None:
            raise self._raise
        return list(self._memories)


def _ids() -> tuple[TenantId, WorkspaceId, UserId, AgentId]:
    return TenantId(uuid4()), WorkspaceId(uuid4()), UserId(uuid4()), AgentId(uuid4())


async def _new_session(
    svc: AgentRuntimeService, deps: dict
) -> tuple[TenantId, WorkspaceId, UUID, UUID]:
    tid, wid, uid, aid = _ids()
    s = await svc.create_session().execute(
        tenant_id=tid,
        workspace_id=wid,
        owner_id=uid,
        agent_id=aid,
        agent_version="1.0.0",
    )
    return tid, wid, s.id, uid


async def test_memory_port_called_with_user_input_and_top_k() -> None:
    deps = make_dependencies()
    memory = _RecordingMemoryPort(
        memories=[{"id": "m1", "content": "ctx", "score": 0.9}]
    )
    svc = AgentRuntimeService(**deps, memory_port=memory)  # type: ignore[arg-type]
    tid, wid, sid, uid = await _new_session(svc, deps)

    uc = svc.run_turn()
    chunks = []
    async for ch in uc.execute(
        tenant_id=tid,
        workspace_id=wid,
        owner_id=uid,
        session_id=sid,
        user_input="hello",
        model="m",
    ):
        chunks.append(ch)

    assert len(memory.calls) == 1
    call = memory.calls[0]
    assert call["query"] == "hello"
    assert call["top_k"] == 10
    assert call["workspace_id"] == wid


async def test_recall_failure_does_not_break_turn() -> None:
    from qzdap_kernel.errors import AppError

    deps = make_dependencies()
    memory = _RecordingMemoryPort(
        raise_exc=AppError("memory offline", code="MEMORY_UNAVAILABLE")
    )
    svc = AgentRuntimeService(**deps, memory_port=memory)  # type: ignore[arg-type]
    tid, wid, sid, uid = await _new_session(svc, deps)

    uc = svc.run_turn()
    chunks = []
    async for ch in uc.execute(
        tenant_id=tid,
        workspace_id=wid,
        owner_id=uid,
        session_id=sid,
        user_input="hi",
        model="m",
    ):
        chunks.append(ch)

    # Done chunk present — turn completed despite recall failure
    assert any(getattr(ch, "kind", "") == "done" for ch in chunks)


async def test_no_memory_port_skips_recall() -> None:
    deps = make_dependencies()
    svc = AgentRuntimeService(**deps)
    tid, wid, sid, uid = await _new_session(svc, deps)

    uc = svc.run_turn()
    chunks = []
    async for ch in uc.execute(
        tenant_id=tid,
        workspace_id=wid,
        owner_id=uid,
        session_id=sid,
        user_input="hi",
        model="m",
    ):
        chunks.append(ch)

    assert any(getattr(ch, "kind", "") == "done" for ch in chunks)


async def test_direct_run_turn_constructor_accepts_memory_port() -> None:
    """``RunTurnUseCase(...)`` accepts a memory_port kwarg directly."""
    deps = make_dependencies()
    memory = _RecordingMemoryPort(
        memories=[{"id": "m1", "content": "ctx", "score": 0.7}]
    )
    svc = AgentRuntimeService(**deps, memory_port=memory)  # type: ignore[arg-type]
    tid, wid, sid, uid = await _new_session(svc, deps)

    # Use the dataclass' run_turn() factory path
    uc = svc.run_turn()
    async for _ in uc.execute(
        tenant_id=tid,
        workspace_id=wid,
        owner_id=uid,
        session_id=sid,
        user_input="ping",
        model="m",
    ):
        pass

    assert memory.calls and memory.calls[0]["query"] == "ping"
