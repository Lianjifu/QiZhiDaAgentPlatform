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
from qzdap_schema.ids import SessionId, TenantId, TurnId, WorkspaceId

from qzdap.modules.agent_runtime.application.ports import (
    EventPublisher,
    LLMPort,
    SessionJournal,
    SessionRepository,
    TurnRepository,
)
from qzdap.modules.agent_runtime.domain import Session, Turn
from qzdap.modules.agent_runtime.domain import TurnStatus as DomainTurnStatus


class InMemoryTurnClaim:
    """会话执行权的内存替身（真实现 = ``PostgresTurnClaim`` ✓）。

    ⚠️ **与仓库共用一个实例** —— 「谁在飞」只有一个真相 ✓（两处各记一份，
    迟早对不上 ✗）。
    """

    def __init__(self) -> None:
        self._held: dict[UUID, UUID] = {}

    async def claim(self, *, tenant_id: UUID, session_id: UUID, turn_id: UUID) -> bool:
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
            session.with_runtime(
                metadata={**session.metadata, "cancel_requested": True}
            )
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
    """轮次**读**端口的替身 —— 行存在 journal 写的那一份里 ✓。

    ⚠️ **不再自己存一份** ✓ —— 停旧写之后轮次只有一个落点 ✓（生产上：
    journal 写 ``session_turns``，本仓库读同一张表 ✓）。
    """

    def __init__(self, journal: InMemorySessionJournal) -> None:
        self._journal = journal

    async def get(self, turn_id: UUID) -> Turn | None:
        row = self._journal.turns.get(turn_id)
        return _row_to_turn(turn_id, row) if row is not None else None

    async def latest_for_session(self, session_id: UUID) -> Turn | None:
        rows = [
            (turn_id, row)
            for turn_id, row in self._journal.turns.items()
            if row["session_id"] == session_id
        ]
        if not rows:
            return None
        turn_id, row = max(rows, key=lambda item: item[1]["started_at"])
        return _row_to_turn(turn_id, row)


def _row_to_turn(turn_id: UUID, row: dict[str, Any]) -> Turn:
    """journal 的行 → 领域 ``Turn`` ✓（状态映射与生产 mapper 一致 ✓）。"""
    status = {"waiting": "running", "cancelled": "denied"}.get(
        str(row.get("status")), str(row.get("status"))
    )
    return Turn(
        id=TurnId(turn_id),
        tenant_id=TenantId(row["tenant_id"]),
        workspace_id=WorkspaceId(row["workspace_id"]),
        session_id=SessionId(row["session_id"]),
        user_input=str(row.get("user_input") or ""),
        status=DomainTurnStatus(status),
        started_at=row["started_at"],
        finished_at=row.get("finished_at"),
        final_response="",
        input_tokens=None,
        output_tokens=None,
        cost_usd=row.get("cost_usd"),
        error_code=row.get("error_code"),
    )


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

    async def synthetic_chunks(self, user_input: str, *, turn_id: UUID) -> list[dict]:
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
        user_input: str | None = None,
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
            "user_input": user_input or "",
            "status": "running",
            "started_at": datetime.now(UTC),
            "finished_at": None,
            "error_code": None,
            "cost_usd": None,
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
            row["finished_at"] = datetime.now(UTC)
            row["cost_usd"] = cost_usd

    async def write_pending_approval(
        self, *, turn_id: UUID, pending: dict[str, Any]
    ) -> None:
        row = self.turns.get(turn_id)
        if row is not None:
            row["pending_approval"] = pending
            row["status"] = "waiting"

    async def find_pending_approval(
        self, *, session_id: UUID, tenant_id: UUID
    ) -> tuple[UUID, dict[str, Any]] | None:
        for turn_id, row in self.turns.items():
            if (
                row.get("session_id") == session_id
                and row.get("status") == "waiting"
                and row.get("pending_approval")
            ):
                return turn_id, dict(row["pending_approval"])
        return None

    async def list_waiting_approval_sessions(self, *, tenant_id: UUID) -> set[UUID]:
        return {
            row["session_id"]
            for row in self.turns.values()
            if row.get("tenant_id") == tenant_id
            and row.get("status") == "waiting"
            and row.get("pending_approval")
        }

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
    journal = InMemorySessionJournal()
    return {
        "sessions": InMemorySessionRepository(InMemoryTurnClaim()),
        # 轮次读仓库与 journal 读**同一份行** ✓（只有一个落点 ✓）。
        "journal": journal,
        "turns": InMemoryTurnRepository(journal),
        "llm": FakeLLM(
            content=llm_content,
            tool_calls=tool_calls,
            raise_on_first_chunk=raise_on_first_chunk,
        ),
        "events": RecordingEventPublisher(),
    }


class InMemoryCatalog:
    """``AgentCatalogService`` 的替身 —— 只认一个 agent ✓。"""

    def __init__(self, agent: Any) -> None:
        self._agent = agent

    async def get_published(self, agent_id: Any) -> Any:  # type: ignore[no-untyped-def]
        return self._agent

    async def get_admin(self, agent_id: Any) -> Any:  # type: ignore[no-untyped-def]
        return self._agent.to_admin_dict()


class InMemoryMessages:
    """``SessionMessagePort`` 的替身 ✓。"""

    def __init__(self) -> None:
        self.rows: list[dict] = []

    async def list_for_session(self, session_id: Any) -> list[dict]:  # type: ignore[no-untyped-def]
        return self.rows

    async def append(self, **kwargs: Any) -> None:  # type: ignore[no-untyped-def]
        self.rows.append(kwargs)

    async def next_seq(self, *, session_id: Any) -> int:  # type: ignore[no-untyped-def]
        return (self.rows[-1]["seq"] + 1) if self.rows else 0


def make_copilot(*, agent: Any, llm: Any = None, tool_port: Any = None) -> Any:
    """装配一个**真的** ``CopilotSessionService``（端口全是内存替身 ✓）。

    ⚠️ 这是**唯一 turn 实现**那条链的单测入口 ✓ —— 旧的 ``AgentRuntimeService``
    门面已删（Session Stage 5b）✓。
    """
    from qzdap_agent_runtime.gateway.idempotency import IdempotencyGuard
    from qzdap_agent_runtime.session.turn_runner import TurnRunner  # noqa: F401

    from qzdap.modules.agent_runtime.adapter.graph.runner import SessionGraphRunner
    from qzdap.modules.agent_runtime.application.copilot import CopilotSessionService

    deps = make_dependencies()
    messages = InMemoryMessages()
    runner = SessionGraphRunner(llm=llm or deps["llm"], tool_port=tool_port)
    journal = deps["journal"]
    deps["messages"] = messages
    service = CopilotSessionService(
        sessions=deps["sessions"],
        turns=deps["turns"],
        messages=messages,
        catalog=InMemoryCatalog(agent),
        events=deps["events"],
        graph=runner,
        idempotency=IdempotencyGuard(InMemoryIdempotencyStore()),
        journal=journal,
        claim=deps["sessions"].claim,
        turn_runner=make_turn_runner(
            graph=runner,
            journal=journal,
            events=deps["events"],
            messages=messages,
            sessions=deps["sessions"],
        ),
    )
    return service, deps


def make_turn_runner(
    *,
    graph: Any,
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
        lifecycle=TurnLifecycle(journal=journal, events=events),
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
