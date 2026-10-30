"""In-memory adapters for the agent runtime application ports — used by unit tests."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from qzdap_agent_runtime.gateway.replay import StoredEvent
from qzdap_agent_runtime.session.state import TurnStatus
from qzdap_kernel.events import DomainEvent
from qzdap_llm.client import ChatRequest, LLMChunk, Usage

from qzdap.modules.agent_runtime.application.ports import (
    EventPublisher,
    LLMPort,
    SessionJournal,
    SessionRepository,
    TurnRepository,
)
from qzdap.modules.agent_runtime.domain import Session, Turn


class InMemoryTurnClaim:
    """会话执行权的内存替身（真实现 = ``PostgresTurnClaim`` ✓）。

    ⚠️ **与仓库共用一个实例** —— 「谁在飞」只有一个真相 ✓（两处各记一份，
    迟早对不上 ✗）。
    """

    def __init__(self) -> None:
        self._held: dict[UUID, UUID] = {}

    async def claim(
        self, *, tenant_id: UUID, session_id: UUID, turn_id: UUID
    ) -> bool:
        if session_id in self._held:
            return False
        self._held[session_id] = turn_id
        return True

    async def release(
        self, *, tenant_id: UUID, session_id: UUID, turn_id: UUID
    ) -> None:
        if self._held.get(session_id) == turn_id:
            self._held.pop(session_id, None)

    async def current_turn_status(
        self, *, tenant_id: UUID, session_id: UUID
    ) -> TurnStatus | None:
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

    async def cancel_requested(self, session_id: UUID) -> bool:
        session = self._by_id.get(session_id)
        if session is None:
            return False
        return bool((session.metadata or {}).get("cancel_requested"))

    async def request_cancel(self, session_id: UUID) -> bool:
        session = self._by_id.get(session_id)
        if session is None:
            return False
        # 「是否在飞」问执行权（不再看 wait_status —— 台账 R3 已清理）✓
        live = self._claim.is_held(session_id) if self._claim is not None else False
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

    async def synthetic_chunks(
        self, user_input: str, *, turn_id: UUID
    ) -> list[dict]:
        """LLM 侧通道（plan / artifact / workflow 事件）—— 真 LLM 默认空。"""
        return []


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


class InMemorySessionJournal(SessionJournal):
    """进程内的轮次 + 事件日志 —— 语义对齐 ``PostgresSessionJournal``。

    **真库的验证在集成测试里**（``tests/integration/test_session_journal.py``）；
    这里只保证单进程内的行为一致（尤其是「事件按 seq 递增、可按 seq 续读」）。
    """

    def __init__(self) -> None:
        self.turns: dict[UUID, dict[str, Any]] = {}
        self.events: dict[UUID, list[StoredEvent]] = {}

    async def start_turn(
        self,
        *,
        turn_id: UUID,
        tenant_id: UUID,
        workspace_id: UUID,
        session_id: UUID,
        idempotency_key: str,
        key_strength: str,
        agent_version: str,
        model_version: str,
        trace_id: str | None = None,
        route_decision: dict[str, Any] | None = None,
    ) -> None:
        self.turns[turn_id] = {
            "tenant_id": tenant_id,
            "workspace_id": workspace_id,
            "session_id": session_id,
            "idempotency_key": idempotency_key,
            "key_strength": key_strength,
            "agent_version": agent_version,
            "model_version": model_version,
            "status": "running",
            "route_decision": route_decision,
        }

    async def finish_turn(
        self,
        *,
        turn_id: UUID,
        status: str,
        error_code: str | None = None,
        cost_usd: float | None = None,
    ) -> None:
        row = self.turns.get(turn_id)
        if row is not None:
            row["status"] = status
            row["error_code"] = error_code

    async def append_event(
        self,
        *,
        turn_id: UUID,
        seq: int,
        event_type: str,
        payload: dict,
    ) -> None:
        self.events.setdefault(turn_id, []).append(
            StoredEvent(seq=seq, event_type=event_type, payload=payload)
        )

    async def mark_delivered(self, *, turn_id: UUID) -> None:
        return None

    # ── 读侧（给测试用；生产读在 PostgresSessionJournal 上）──────────────

    async def get_events(
        self, turn_id: UUID, *, tenant_id: UUID, after_seq: int = 0
    ) -> list[StoredEvent]:
        row = self.turns.get(turn_id)
        if row is None or row["tenant_id"] != tenant_id:
            return []
        return [e for e in self.events.get(turn_id, []) if e.seq > after_seq]

    async def get_turn_status(self, turn_id: UUID, *, tenant_id: UUID) -> str | None:
        row = self.turns.get(turn_id)
        if row is None or row["tenant_id"] != tenant_id:
            return None
        return str(row["status"])


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


def make_turn_runner(
    *,
    graph: Any,
    turns: TurnRepository,
    journal: SessionJournal,
    events: EventPublisher,
    messages: Any,
    sessions: SessionRepository,
) -> Any:
    """契约层的**真** ``TurnRunner`` + 模块侧的真实适配器 ✓。

    ⚠️ 执行器是真的 graph（产出 chunk）—— 端口全是模块侧的真实实现
    （生命周期 / 会话状态 / 取消）✓，所以单测**仍然覆盖编排** ✓
    （不是「fake 掉编排」✗）。
    """
    from qzdap_agent_runtime.session.turn_runner import TurnRunner

    from qzdap.modules.agent_runtime.adapter.turn.cancel import SqlCancelProbe
    from qzdap.modules.agent_runtime.adapter.turn.executor import (
        SessionGraphExecutor,
    )
    from qzdap.modules.agent_runtime.adapter.turn.lifecycle import TurnLifecycle
    from qzdap.modules.agent_runtime.adapter.turn.session_state import SqlSessionState

    return TurnRunner(
        executor=SessionGraphExecutor(graph),
        lifecycle=TurnLifecycle(turns=turns, journal=journal, events=events),
        messages=messages,
        session_state=SqlSessionState(sessions),
        cancel=SqlCancelProbe(sessions),
    )


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
