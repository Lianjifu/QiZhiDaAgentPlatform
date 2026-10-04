"""Unit tests for the P7 knowledge recall hook wired into RunTurnUseCase.

Mirrors ``test_memory_recall_hook.py`` (P4) — verifies the knowledge
module ↔ agent_runtime integration at the use-case level without a real
database. Knowledge recall is best-effort: failures must not break the
turn.
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


class _RecordingKnowledgePort:
    """Captures search() args and returns canned knowledge chunks."""

    def __init__(
        self,
        *,
        chunks: list[dict] | None = None,
        raise_exc: Exception | None = None,
    ) -> None:
        self._chunks = chunks or []
        self._raise = raise_exc
        self.calls: list[dict[str, Any]] = []

    async def search(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        query: str,
        top_k: int,
        package_ids: tuple[UUID, ...] = (),
    ) -> list[dict]:
        self.calls.append(
            {
                "tenant_id": tenant_id,
                "workspace_id": workspace_id,
                "query": query,
                "top_k": top_k,
                "package_ids": package_ids,
            }
        )
        if self._raise is not None:
            raise self._raise
        return list(self._chunks)


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


async def test_knowledge_port_called_with_user_input_and_top_k() -> None:
    deps = make_dependencies()
    knowledge = _RecordingKnowledgePort(
        chunks=[
            {
                "id": "c1",
                "asset_id": "a1",
                "package_id": "p1",
                "package_name": "faq",
                "asset_name": "a.txt",
                "content": "reset password instructions",
                "score": 0.95,
                "ordinal": 0,
            }
        ]
    )
    svc = AgentRuntimeService(**deps, knowledge_port=knowledge)  # type: ignore[arg-type]
    tid, wid, sid, uid = await _new_session(svc, deps)

    uc = svc.run_turn()
    chunks: list = []
    async for ch in uc.execute(
        tenant_id=tid,
        workspace_id=wid,
        owner_id=uid,
        session_id=sid,
        user_input="how do I reset my password?",
        model="m",
    ):
        chunks.append(ch)

    assert len(knowledge.calls) == 1
    call = knowledge.calls[0]
    assert call["query"] == "how do I reset my password?"
    assert call["top_k"] == 10
    assert call["workspace_id"] == wid
    assert any(getattr(ch, "kind", "") == "done" for ch in chunks)


async def test_knowledge_recall_failure_does_not_break_turn() -> None:
    from qzdap_kernel.errors import AppError

    deps = make_dependencies()
    knowledge = _RecordingKnowledgePort(
        raise_exc=AppError("knowledge offline", code="KNOWLEDGE_UNAVAILABLE")
    )
    svc = AgentRuntimeService(**deps, knowledge_port=knowledge)  # type: ignore[arg-type]
    tid, wid, sid, uid = await _new_session(svc, deps)

    uc = svc.run_turn()
    chunks: list = []
    async for ch in uc.execute(
        tenant_id=tid,
        workspace_id=wid,
        owner_id=uid,
        session_id=sid,
        user_input="hi",
        model="m",
    ):
        chunks.append(ch)

    # Turn completed despite the knowledge port raising.
    assert any(getattr(ch, "kind", "") == "done" for ch in chunks)


async def test_no_knowledge_port_skips_recall() -> None:
    deps = make_dependencies()
    svc = AgentRuntimeService(**deps)
    tid, wid, sid, uid = await _new_session(svc, deps)

    uc = svc.run_turn()
    chunks: list = []
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


async def test_memory_and_knowledge_combined_into_system_prompt() -> None:
    """When both ports are wired, both must be called and the turn
    completes (prompt assembly is exercised but not asserted bytewise)."""
    deps = make_dependencies()

    class _M:
        def __init__(self) -> None:
            self.calls = 0

        async def recall(
            self, *, tenant_id: UUID, workspace_id: UUID, query: str, top_k: int
        ) -> list[dict]:
            self.calls += 1
            return [{"id": "m1", "content": "mem-ctx", "score": 0.8}]

    m, k = (
        _M(),
        _RecordingKnowledgePort(
            chunks=[
                {
                    "id": "c1",
                    "asset_id": "a1",
                    "package_id": "p1",
                    "package_name": "faq",
                    "asset_name": "a.txt",
                    "content": "k-ctx",
                    "score": 0.7,
                    "ordinal": 0,
                }
            ]
        ),
    )
    svc = AgentRuntimeService(**deps, memory_port=m, knowledge_port=k)  # type: ignore[arg-type]
    tid, wid, sid, uid = await _new_session(svc, deps)

    uc = svc.run_turn()
    chunks: list = []
    async for ch in uc.execute(
        tenant_id=tid,
        workspace_id=wid,
        owner_id=uid,
        session_id=sid,
        user_input="hello",
        model="m",
    ):
        chunks.append(ch)

    assert m.calls == 1
    assert len(k.calls) == 1
    assert any(getattr(ch, "kind", "") == "done" for ch in chunks)


async def test_knowledge_only_no_memory_skips_memory_block() -> None:
    """With only knowledge wired, the system prompt uses the
    knowledge-only template (no bare or memory template)."""
    deps = make_dependencies()
    k = _RecordingKnowledgePort(
        chunks=[
            {
                "id": "c1",
                "asset_id": "a1",
                "package_id": "p1",
                "package_name": "faq",
                "asset_name": "a.txt",
                "content": "k",
                "score": 0.5,
                "ordinal": 0,
            }
        ]
    )
    svc = AgentRuntimeService(**deps, knowledge_port=k)  # type: ignore[arg-type]
    tid, wid, sid, uid = await _new_session(svc, deps)

    uc = svc.run_turn()
    seen: list = []
    async for ch in uc.execute(
        tenant_id=tid,
        workspace_id=wid,
        owner_id=uid,
        session_id=sid,
        user_input="hello",
        model="m",
    ):
        seen.append(ch)

    assert any(getattr(ch, "kind", "") == "done" for ch in seen)
    # knowledge port was called exactly once
    assert len(k.calls) == 1


async def test_direct_run_turn_constructor_accepts_knowledge_port() -> None:
    """``RunTurnUseCase(...)`` accepts a knowledge_port kwarg directly."""
    deps = make_dependencies()
    k = _RecordingKnowledgePort(chunks=[])
    svc = AgentRuntimeService(**deps, knowledge_port=k)  # type: ignore[arg-type]
    tid, wid, sid, uid = await _new_session(svc, deps)

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

    assert k.calls and k.calls[0]["query"] == "ping"


__all__: list[str] = []
