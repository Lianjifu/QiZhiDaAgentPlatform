"""In-memory adapters for the agent runtime application ports — used by unit tests."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

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

    async def try_claim(self, session_id: UUID) -> bool:
        session = self._by_id.get(session_id)
        if session is None:
            return False
        if session.wait_status == "running":
            return False
        await self.update(session.with_runtime(wait_status="running"))
        return True

    async def release(self, session_id: UUID) -> None:
        session = self._by_id.get(session_id)
        if session is None or session.wait_status != "running":
            return
        await self.update(session.with_runtime(wait_status="idle"))

    async def cancel_requested(self, session_id: UUID) -> bool:
        session = self._by_id.get(session_id)
        if session is None:
            return False
        return bool((session.metadata or {}).get("cancel_requested"))

    async def request_cancel(self, session_id: UUID) -> bool:
        session = self._by_id.get(session_id)
        if session is None:
            return False
        live = session.wait_status == "running"
        await self.update(
            session.with_runtime(metadata={**session.metadata, "cancel_requested": True})
        )
        return live

    async def clear_cancel(self, session_id: UUID) -> None:
        session = self._by_id.get(session_id)
        if session is None:
            return
        meta = dict(session.metadata or {})
        if not meta.pop("cancel_requested", None):
            return
        await self.update(session.with_runtime(metadata=meta))

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
        return max(turns, key=lambda t: t.started_at)


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


class InMemoryIdempotencyStore:
    """幂等守卫的测试替身 —— 语义对齐 ``PostgresIdempotencyStore``，只在进程内。

    **并发语义的真实验证在集成测试里**（``tests/integration/test_idempotency_store.py``，
    真库 + 真并发）；这里只保证单进程内的判定一致。
    """

    def __init__(self) -> None:
        self._rows: dict[tuple[Any, Any, Any, str], dict[str, Any]] = {}
        # weak 行只记录、不查重 —— 单独放一份, 不参与按键查找.
        self._weak_rows: list[dict[str, Any]] = []

    async def claim(
        self,
        scope: Any,
        key: Any,
        *,
        payload_hash: str = "",
        external_message_id: str | None = None,
        trace_id: str = "",
    ) -> Any:
        from qzdap_agent_runtime.gateway.types import IdempotencyDecision

        k = (scope.tenant_id, scope.workspace_id, scope.channel_id, key.value)
        row = self._rows.get(k)
        now = datetime.now(UTC)
        if row is not None:
            if row["expires_at"] <= now:
                row = None  # 过期 → 当作不存在
            elif row["status"] == "completed":
                return IdempotencyDecision(
                    outcome="duplicate",
                    key_strength=key.strength,
                    row_id=row["id"],
                    status=row["status"],
                    turn_id=row["turn_id"],
                    expires_at=row["expires_at"],
                )
            else:
                return IdempotencyDecision(
                    outcome="in_progress",
                    key_strength=key.strength,
                    row_id=row["id"],
                    status=row["status"],
                    turn_id=row["turn_id"],
                    expires_at=row["expires_at"],
                )
        row = {
            "id": uuid4(),
            "status": "claimed",
            "turn_id": None,
            "expires_at": key.expires_at,
        }
        self._rows[k] = row
        return IdempotencyDecision(
            outcome="new",
            key_strength=key.strength,
            row_id=row["id"],
            status="claimed",
            turn_id=None,
            expires_at=row["expires_at"],
        )

    async def record_weak(
        self,
        scope: Any,
        key: Any,
        *,
        payload_hash: str = "",
        trace_id: str = "",
    ) -> Any:
        from qzdap_agent_runtime.gateway.types import IdempotencyDecision

        row = {
            "id": uuid4(),
            "status": "received",
            "turn_id": None,
            "expires_at": key.expires_at,
        }
        # weak 永不判重 —— 每次都新落一行, 且不参与按键查找.
        self._weak_rows.append(row)
        return IdempotencyDecision(
            outcome="new",
            key_strength="weak",
            row_id=row["id"],
            status="received",
            turn_id=None,
            expires_at=row["expires_at"],
        )

    async def mark_completed(
        self, row_id: UUID, *, turn_id: UUID | None = None
    ) -> None:
        for row in [*self._rows.values(), *self._weak_rows]:
            if row["id"] == row_id:
                row["status"] = "completed"
                row["turn_id"] = turn_id
                return

    async def release(self, row_id: UUID) -> None:
        for k, row in list(self._rows.items()):
            if row["id"] == row_id:
                del self._rows[k]
                return
        self._weak_rows = [row for row in self._weak_rows if row["id"] != row_id]



_ = Any  # keep typing import alive for Any in stub annotations
