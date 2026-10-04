"""In-memory adapters for the agent runtime application ports — used by unit tests."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

from qzdap_kernel.events import DomainEvent
from qzdap_llm.client import ChatRequest, LLMChunk, Usage

from qzdap.modules.agent_runtime.application.ports import (
    EventPublisher,
    LLMPort,
    SessionRepository,
    TurnRepository,
)
from qzdap.modules.agent_runtime.domain import Session, Turn


class InMemorySessionRepository(SessionRepository):
    def __init__(self) -> None:
        self._by_id: dict[UUID, Session] = {}

    async def add(self, session: Session) -> None:
        self._by_id[session.id] = session

    async def update(self, session: Session) -> None:
        self._by_id[session.id] = session

    async def get(self, session_id: UUID) -> Session | None:
        return self._by_id.get(session_id)

    async def list_for_owner(
        self, owner_id: UUID, *, limit: int = 50, offset: int = 0
    ) -> list[Session]:
        items = sorted(
            (s for s in self._by_id.values() if s.owner_id == owner_id),
            key=lambda s: s.created_at,
            reverse=True,
        )
        return items[offset : offset + limit]


class InMemoryTurnRepository(TurnRepository):
    def __init__(self) -> None:
        self._by_id: dict[UUID, Turn] = {}

    async def add(self, turn: Turn) -> None:
        self._by_id[turn.id] = turn

    async def get(self, turn_id: UUID) -> Turn | None:
        return self._by_id.get(turn_id)


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
    return {
        "sessions": InMemorySessionRepository(),
        "turns": InMemoryTurnRepository(),
        "llm": FakeLLM(
            content=llm_content,
            tool_calls=tool_calls,
            raise_on_first_chunk=raise_on_first_chunk,
        ),
        "events": RecordingEventPublisher(),
    }


_ = Any  # keep typing import alive for Any in stub annotations
