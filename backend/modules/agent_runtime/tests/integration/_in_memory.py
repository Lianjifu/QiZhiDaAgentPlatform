"""In-memory adapters for the agent runtime application ports — used by unit tests."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

from qzdap.modules.agent_runtime.application.ports import (
    EventPublisher,
    LLMPort,
    SessionRepository,
    TurnRepository,
)
from qzdap.modules.agent_runtime.domain import Session, Turn
from qzdap_agent_runtime.session.state import TurnStatus
from qzdap_kernel.events import DomainEvent
from qzdap_llm.client import ChatRequest, LLMChunk, Usage


class InMemoryTurnClaim:
    """会话执行权的内存替身（真实现 = ``PostgresTurnClaim`` ✓）。"""

    def __init__(self) -> None:
        self._held: dict[UUID, UUID] = {}

    async def claim(self, *, tenant_id: UUID, session_id: UUID, turn_id: UUID) -> bool:
        if session_id in self._held:
            return False
        self._held[session_id] = turn_id
        return True

    async def release(self, *, tenant_id: UUID, session_id: UUID, turn_id: UUID) -> None:
        if self._held.get(session_id) == turn_id:
            self._held.pop(session_id, None)

    async def current_turn_status(self, *, tenant_id: UUID, session_id: UUID) -> TurnStatus | None:
        return TurnStatus.RUNNING if session_id in self._held else None

    def is_held(self, session_id: UUID) -> bool:
        return session_id in self._held


class InMemorySessionRepository(SessionRepository):
    def __init__(self, claim: InMemoryTurnClaim | None = None) -> None:
        self._by_id: dict[UUID, Session] = {}
        self._claim = claim

    @property
    def claim(self) -> InMemoryTurnClaim:
        """执行权替身 —— 与本仓库**共用同一个实例** ✓（只有一个真相）。"""
        if self._claim is None:
            self._claim = InMemoryTurnClaim()
        return self._claim

    async def add(self, session: Session) -> None:
        self._by_id[session.id] = session

    async def update(self, session: Session) -> None:
        self._by_id[session.id] = session

    async def get(self, session_id: UUID) -> Session | None:
        return self._by_id.get(session_id)

    async def list_for_owner(
        self, tenant_id: UUID, owner_id: UUID, *, limit: int = 50, offset: int = 0
    ) -> list[Session]:
        items = sorted(
            (
                s
                for s in self._by_id.values()
                if s.tenant_id == tenant_id and s.owner_id == owner_id
            ),
            key=lambda s: s.created_at,
            reverse=True,
        )
        return items[offset : offset + limit]

    async def list_for_owner_workspace(
        self,
        tenant_id: UUID,
        owner_id: UUID,
        workspace_id: UUID,
        *,
        limit: int = 200,
    ) -> list[Session]:
        items = sorted(
            (
                s
                for s in self._by_id.values()
                if s.tenant_id == tenant_id
                and s.owner_id == owner_id
                and s.workspace_id == workspace_id
            ),
            key=lambda s: s.created_at,
            reverse=True,
        )
        return items[:limit]


class InMemoryTurnRepository(TurnRepository):
    def __init__(self) -> None:
        self._by_id: dict[UUID, Turn] = {}

    async def add(self, turn: Turn) -> None:
        self._by_id[turn.id] = turn

    async def get(self, turn_id: UUID) -> Turn | None:
        return self._by_id.get(turn_id)

    async def latest_for_session(self, session_id: UUID) -> Turn | None:
        turns = [t for t in self._by_id.values() if t.session_id == session_id]
        if not turns:
            return None
        return max(turns, key=lambda t: t.created_at)


class FakeLLM(LLMPort):
    """Test double: yields a single 'echo' message chunk + a final stop chunk."""

    def __init__(
        self,
        *,
        content: str = "echo",
        input_tokens: int = 3,
        output_tokens: int = 2,
        tool_calls: list[dict] | None = None,
        raise_on_first_chunk: Exception | None = None,
    ) -> None:
        self._content = content
        self._input_tokens = input_tokens
        self._output_tokens = output_tokens
        self._tool_calls = tool_calls
        self._raise = raise_on_first_chunk

    async def stream(self, req: ChatRequest) -> AsyncIterator[LLMChunk]:
        if self._raise is not None:
            raise self._raise
        yield LLMChunk(model=req.model, delta=self._content)
        if self._tool_calls:
            yield LLMChunk(model=req.model, delta="", tool_calls=self._tool_calls)
        yield LLMChunk(
            model=req.model,
            delta="",
            finish_reason="stop",
            usage=Usage(
                input_tokens=self._input_tokens,
                output_tokens=self._output_tokens,
            ),
        )


class RecordingEventPublisher(EventPublisher):
    """Records published events for assertions."""

    def __init__(self) -> None:
        self.events: list[DomainEvent] = []

    async def publish(
        self,
        event: DomainEvent,
        *,
        tenant_id: UUID,
        workspace_id: UUID | None,
        trace_id: str | None = None,
    ) -> None:
        self.events.append(event)


def make_dependencies(
    *,
    llm_content: str = "echo",
    tool_calls: list[dict] | None = None,
    raise_on_first_chunk: Exception | None = None,
):  # type: ignore[no-untyped-def]
    # ⚠️ 执行权（互斥）与仓库**共用一个 claim 实例** —— 「谁在飞」只有一个
    # 真相 ✓（台账 R3：旧的 wait_status CAS 已迁走）。
    return {
        "sessions": InMemorySessionRepository(InMemoryTurnClaim()),
        "turns": InMemoryTurnRepository(),
        "llm": FakeLLM(
            content=llm_content,
            tool_calls=tool_calls,
            raise_on_first_chunk=raise_on_first_chunk,
        ),
        "events": RecordingEventPublisher(),
    }


_ = Any  # keep typing import alive for Any in stub annotations
