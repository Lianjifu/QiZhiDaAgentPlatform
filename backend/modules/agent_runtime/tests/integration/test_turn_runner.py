"""**唯一 turn 实现**（契约层的 ``TurnRunner``）—— **真库**。

覆盖 Session Stage 3b 的落点（Session 方案 §6 / §7）：

跑一轮之后，**每一张表**都该有正确的行：

| 表 | 断言 |
|---|---|
| ``agent_turns``（旧） | 轮次行，状态 ``succeeded`` ✓ |
| ``session_turns``（新） | 轮次行，状态 ``succeeded`` + **成本归属** ``cost_usd`` ✓ |
| ``session_events`` | 每个 chunk 一行，``seq`` 从 1 连续递增 ✓ |
| ``agent_session_messages``（旧） | 用户消息 + 助手消息 ✓（双写期） |
| ``session_messages``（新） | 同上，且 ``session_seq`` 会话内单调 ✓ |
| ``agent_sessions`` | 会话行的 ``preview`` 更新 ✓ |

⚠️ **执行器是假的**（产出固定的 chunk）—— 这里要验的是**编排的落库效果**，
不是 graph 怎么跑（那是 Agent 层的事 ✓）。
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from qzdap_agent_runtime.session.approval import arguments_digest
from qzdap_agent_runtime.session.turn_runner import (
    AgentSnapshot,
    TurnRequest,
    TurnRunner,
)
from qzdap_schema.dtos.turn import (
    ApprovalRequiredChunk,
    DoneChunk,
    MessageChunk,
    UsageChunk,
)
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

_DDL = [
    """
CREATE TABLE "{schema}".agent_sessions (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    owner_id uuid NOT NULL,
    agent_id uuid NOT NULL,
    agent_version varchar(64) NOT NULL,
    status varchar(16) NOT NULL DEFAULT 'open',
    closed_at timestamptz,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    graph_state jsonb NOT NULL DEFAULT '{}'::jsonb,
    -- ⚠️ **摘要是独立的一列** ✓（Context 方案 §5.1 ✓）—— ORM 现在映射它 ✓
    rolling_summary text NOT NULL DEFAULT '',
    wait_status varchar(32) NOT NULL DEFAULT 'idle',
    current_revision integer NOT NULL DEFAULT 0,
    current_turn_id uuid,
    agent_version_pinned varchar(64),
    channel_session_key varchar(512),
    next_ingress_seq integer NOT NULL DEFAULT 0,
    last_completed_seq integer NOT NULL DEFAULT 0,
    next_message_seq integer NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
)
""",
    """
CREATE TABLE "{schema}".agent_turns (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    session_id uuid NOT NULL,
    user_input text NOT NULL,
    started_at timestamptz NOT NULL DEFAULT now(),
    status varchar(16) NOT NULL DEFAULT 'running',
    finished_at timestamptz,
    final_response text,
    error_code varchar(64),
    input_tokens integer,
    output_tokens integer,
    cost_usd numeric(12,6),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
)
""",
    """
CREATE TABLE "{schema}".session_turns (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    session_id uuid NOT NULL,
    idempotency_key varchar(128) NOT NULL,
    key_strength varchar(8) NOT NULL DEFAULT 'strong',
    status varchar(16) NOT NULL DEFAULT 'running',
    started_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    trace_id varchar(64),
    agent_version varchar(64) NOT NULL,
    model_version varchar(64) NOT NULL,
    user_input text,
    cost_usd numeric(12,6),
    expected_revision integer NOT NULL DEFAULT 0,
    error_code varchar(64),
    pending_approval jsonb,
    cancel_requested boolean NOT NULL DEFAULT false,
    ingress_seq integer,
    route_decision jsonb,
    agent_decision jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT session_turns_status_enum CHECK (
        status IN ('queued','running','waiting','succeeded','failed','cancelled')
    )
)
""",
    """
CREATE TABLE "{schema}".session_messages (
    turn_id uuid NOT NULL REFERENCES "{schema}".session_turns (id) ON DELETE CASCADE,
    seq integer NOT NULL,
    role varchar(16) NOT NULL,
    content text NOT NULL,
    message_id varchar(64),
    metadata_ jsonb,
    session_id uuid NOT NULL,
    session_seq integer NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (turn_id, seq)
)
""",
    """
CREATE UNIQUE INDEX uq_session_messages_session_seq
    ON "{schema}".session_messages (session_id, session_seq)
""",
    """
CREATE TABLE "{schema}".agent_session_messages (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    session_id uuid NOT NULL,
    turn_id uuid,
    seq integer NOT NULL,
    role varchar(32) NOT NULL,
    content text NOT NULL,
    tool_name varchar(128) NOT NULL DEFAULT '',
    extra jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
)
""",
    """
CREATE TABLE "{schema}".session_events (
    turn_id uuid NOT NULL REFERENCES "{schema}".session_turns (id) ON DELETE CASCADE,
    seq integer NOT NULL,
    event_type varchar(64) NOT NULL,
    payload jsonb NOT NULL,
    delivery_status varchar(16) NOT NULL DEFAULT 'pending',
    delivery_attempts integer NOT NULL DEFAULT 0,
    delivered_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (turn_id, seq),
    CONSTRAINT session_events_status_enum CHECK (
        delivery_status IN ('pending','delivered','failed','dead_letter')
    )
)
""",
]


class _FakeExecutor:
    """假的执行器 —— 产出固定的 chunk 序列 ✓。"""

    def __init__(self, *, turn_id: UUID) -> None:
        self._turn_id = turn_id

    async def run(self, *, request: TurnRequest):  # type: ignore[no-untyped-def]
        yield MessageChunk(
            turn_id=request.turn_id,
            seq=1,
            content="你好",
        )
        yield UsageChunk(
            turn_id=request.turn_id,
            seq=2,
            input_tokens=10,
            output_tokens=5,
            cache_read_tokens=0,
            cache_write_tokens=0,
            cost_usd=0.01,
        )
        yield DoneChunk(
            turn_id=request.turn_id,
            seq=3,
            final_message="你好，我是助手",
        )

    def latest_state(self):  # type: ignore[no-untyped-def]
        return {"rolling_summary": "摘要"}


class _ApprovalExecutor:
    """产出「需要审批」chunk 的执行器 ✓。"""

    def __init__(self, *, approval_id: UUID) -> None:
        self._approval_id = approval_id

    async def run(self, *, request: TurnRequest):  # type: ignore[no-untyped-def]
        yield ApprovalRequiredChunk(
            turn_id=request.turn_id,
            seq=1,
            approval_id=self._approval_id,
            tool_name="danger_tool",
            arguments={"path": "/"},
        )

    def latest_state(self):  # type: ignore[no-untyped-def]
        return {}


class _NoopMessages:
    """消息端口的空实现 ✓（这里只关心轮次行的落库）。"""

    async def next_seq(self, *, session_id):  # type: ignore[no-untyped-def]
        return 0

    async def append(self, **kwargs):  # type: ignore[no-untyped-def]
        return None


class _RecordingEvents:
    def __init__(self) -> None:
        self.events: list[Any] = []

    async def publish(self, event, **kwargs) -> None:  # type: ignore[no-untyped-def]
        self.events.append(event)


@pytest.fixture
async def turn_ctx():
    url = os.environ.get("QZDAP_TEST_DATABASE_URL")
    if not url:
        pytest.skip("QZDAP_TEST_DATABASE_URL is not set")
    schema = "turnrun_" + uuid.uuid4().hex
    admin = create_async_engine(url)
    async with admin.connect() as conn:
        await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        for statement in _DDL:
            await conn.execute(text(statement.replace("{schema}", schema)))
        await conn.commit()

    engine = create_async_engine(
        url, connect_args={"server_settings": {"search_path": schema}}
    )
    from qzdap_persistence.session_factory import SessionFactory

    factory = SessionFactory(engine)
    try:
        yield factory
    finally:
        await engine.dispose()
        async with admin.connect() as conn:
            await conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            await conn.commit()
        await admin.dispose()


async def _session_row(factory, *, session_id: UUID, tenant_id: UUID) -> None:
    async with factory.session() as session, session.begin():
        await session.execute(
            text(
                "INSERT INTO agent_sessions "
                "(id, tenant_id, workspace_id, owner_id, agent_id, agent_version, "
                " metadata) "
                "VALUES (:id, :tenant, :ws, :owner, :agent, 'v1', "
                " '{\"title_auto\": true}'::jsonb)"
            ),
            {
                "id": session_id,
                "tenant": tenant_id,
                "ws": uuid4(),
                "owner": uuid4(),
                "agent": uuid4(),
            },
        )


@pytest.mark.asyncio
async def test_a_turn_lands_only_in_the_new_table(turn_ctx) -> None:  # type: ignore[no-untyped-def]
    """轮次**只落新表** ✓ —— 旧表停写（S-15b ✓）→ 旧表必须是空的 ✓。"""
    from qzdap.modules.agent_runtime.adapter.persistence.repositories import (
        SqlSessionRepository,
    )
    from qzdap.modules.agent_runtime.adapter.persistence.session_journal import (
        PostgresSessionJournal,
    )
    from qzdap.modules.agent_runtime.adapter.persistence.session_messages import (
        PostgresSessionMessageStore,
    )
    from qzdap.modules.agent_runtime.adapter.turn.cancel import SqlCancelProbe
    from qzdap.modules.agent_runtime.adapter.turn.lifecycle import TurnLifecycle
    from qzdap.modules.agent_runtime.adapter.turn.session_state import SqlSessionState

    tenant = uuid4()
    session_id = uuid4()
    turn_id = uuid4()
    await _session_row(turn_ctx, session_id=session_id, tenant_id=tenant)

    events = _RecordingEvents()
    # ⚠️ 生产里这些适配器共用**请求级**的 DB 会话 —— 测试里也一样 ✓
    async with turn_ctx.session() as db_session:
        sessions = SqlSessionRepository(db_session)
        messages = PostgresSessionMessageStore(db_session)
        runner = TurnRunner(
            executor=_FakeExecutor(turn_id=turn_id),
            lifecycle=TurnLifecycle(
                journal=PostgresSessionJournal(turn_ctx),
                events=events,  # type: ignore[arg-type]
            ),
            messages=messages,
            session_state=SqlSessionState(sessions),
            cancel=SqlCancelProbe(sessions),
        )
        request = TurnRequest(
            tenant_id=tenant,
            workspace_id=uuid4(),
            owner_id=uuid4(),
            session_id=session_id,
            turn_id=turn_id,
            user_input="你好",
            idempotency_key="k1",
            key_strength="strong",
            agent=AgentSnapshot(
                agent_id=uuid4(), agent_version="v1", model="default", raw=None
            ),
            # 会话元数据的快照（生产里由 copilot 从会话行读出来 ✓）——
            # ``title_auto`` 让这一轮顺手把标题定下来 ✓。
            session_metadata={"title_auto": True},
        )
        chunks = [chunk async for chunk in runner.run(request=request)]
        assert [chunk.kind for chunk in chunks] == ["message", "usage", "done"]
        await db_session.commit()

    async with turn_ctx.session() as session:
        old_turn_rows = (
            await session.execute(
                text("SELECT id FROM agent_turns WHERE id = :id"),
                {"id": turn_id},
            )
        ).all()
        new_turn = (
            await session.execute(
                text(
                    "SELECT status, cost_usd, finished_at FROM session_turns "
                    "WHERE id = :id"
                ),
                {"id": turn_id},
            )
        ).one()
        events_rows = (
            await session.execute(
                text("SELECT seq, event_type FROM session_events ORDER BY seq")
            )
        ).all()
        old_msgs = (
            await session.execute(
                text("SELECT role, content FROM agent_session_messages ORDER BY seq")
            )
        ).all()
        old_msg_count = (
            await session.execute(text("SELECT count(*) FROM agent_session_messages"))
        ).scalar_one()
        new_msgs = (
            await session.execute(
                text(
                    "SELECT role, content, session_seq FROM session_messages "
                    "ORDER BY session_seq"
                )
            )
        ).all()
        session_row = (
            await session.execute(
                text(
                    "SELECT metadata->>'preview' AS preview, metadata "
                    "FROM agent_sessions WHERE id = :id"
                ),
                {"id": session_id},
            )
        ).one()

    # ⚠️ **旧表不再写** ✓（停旧写 S-15b ✓）—— 这一轮一行都没有 ✓。
    assert old_turn_rows == []
    assert old_msg_count == 0
    # 新表轮次：成功 + **成本归属** ✓
    assert new_turn[0] == "succeeded"
    assert float(new_turn[1]) == pytest.approx(0.01)
    assert new_turn[2] is not None
    # 事件：每个 chunk 一行，seq 从 1 连续 ✓
    assert [row[0] for row in events_rows] == [1, 2, 3]
    assert [row[1] for row in events_rows] == ["message", "usage", "done"]
    # 消息：新表有（session_seq 单调 ✓），旧表空 ✓
    assert old_msgs == []
    assert [(r[0], r[1]) for r in new_msgs] == [
        ("user", "你好"),
        ("assistant", "你好，我是助手"),
    ]
    assert [r[2] for r in new_msgs] == [1, 2]
    # 会话行：预览 + 自动标题 ✓
    assert session_row[0] == "你好，我是助手"
    assert session_row[1]["title"] == "你好"


@pytest.mark.asyncio
async def test_a_failed_turn_lands_as_failed(turn_ctx) -> None:  # type: ignore[no-untyped-def]
    """一个 chunk 都没产出就失败 → 轮次落到 ``failed`` ✓（不是永远 running）。"""
    from qzdap.modules.agent_runtime.adapter.persistence.session_journal import (
        PostgresSessionJournal,
    )
    from qzdap.modules.agent_runtime.adapter.turn.lifecycle import TurnLifecycle

    tenant = uuid4()
    session_id = uuid4()
    turn_id = uuid4()
    await _session_row(turn_ctx, session_id=session_id, tenant_id=tenant)

    class _BoomExecutor:
        async def run(self, *, request):  # type: ignore[no-untyped-def]
            raise RuntimeError("no provider")
            yield  # pragma: no cover

        def latest_state(self):  # type: ignore[no-untyped-def]
            return {}

    async with turn_ctx.session() as db_session:
        lifecycle = TurnLifecycle(
            journal=PostgresSessionJournal(turn_ctx),
            events=_RecordingEvents(),  # type: ignore[arg-type]
        )
        runner = TurnRunner(
            executor=_BoomExecutor(),
            lifecycle=lifecycle,
            messages=_NoopMessages(),  # type: ignore[arg-type]
            session_state=None,  # type: ignore[arg-type]
            cancel=None,  # type: ignore[arg-type]
        )
        request = TurnRequest(
            tenant_id=tenant,
            workspace_id=uuid4(),
            owner_id=uuid4(),
            session_id=session_id,
            turn_id=turn_id,
            user_input="你好",
            idempotency_key="k1",
            key_strength="strong",
            agent=AgentSnapshot(
                agent_id=uuid4(), agent_version="v1", model="default", raw=None
            ),
        )
        with pytest.raises(RuntimeError):
            async for _ in runner.run(request=request):
                pass
        await db_session.commit()

    async with turn_ctx.session() as session:
        row = (
            await session.execute(
                text("SELECT status, error_code FROM session_turns WHERE id = :id"),
                {"id": turn_id},
            )
        ).one()
    assert row[0] == "failed"
    assert row[1] == "TURN_FAILED"


@pytest.mark.asyncio
async def test_the_pending_approval_lands_on_the_turn_row(turn_ctx) -> None:  # type: ignore[no-untyped-def]
    """审批挂起 → ``session_turns.pending_approval`` 落库 + 状态 ``waiting`` ✓。

    ⚠️ **只在内存里 = 进程重启后审批永久卡死** ✗✗ —— 落库是恢复的前提 ✓。
    """
    from qzdap.modules.agent_runtime.adapter.persistence.repositories import (
        SqlSessionRepository,
    )
    from qzdap.modules.agent_runtime.adapter.persistence.session_journal import (
        PostgresSessionJournal,
    )
    from qzdap.modules.agent_runtime.adapter.turn.lifecycle import TurnLifecycle
    from qzdap.modules.agent_runtime.adapter.turn.session_state import SqlSessionState

    tenant = uuid4()
    session_id = uuid4()
    turn_id = uuid4()
    approval_id = uuid4()
    await _session_row(turn_ctx, session_id=session_id, tenant_id=tenant)

    async with turn_ctx.session() as db_session:
        runner = TurnRunner(
            executor=_ApprovalExecutor(approval_id=approval_id),
            lifecycle=TurnLifecycle(
                journal=PostgresSessionJournal(turn_ctx),
                events=_RecordingEvents(),  # type: ignore[arg-type]
            ),
            messages=_NoopMessages(),  # type: ignore[arg-type]
            session_state=SqlSessionState(SqlSessionRepository(db_session)),
            cancel=None,  # type: ignore[arg-type]
        )
        request = TurnRequest(
            tenant_id=tenant,
            workspace_id=uuid4(),
            owner_id=uuid4(),
            session_id=session_id,
            turn_id=turn_id,
            user_input="清理磁盘",
            idempotency_key="k1",
            key_strength="strong",
            agent=AgentSnapshot(
                agent_id=uuid4(), agent_version="v1", model="default", raw=None
            ),
        )
        chunks = [chunk async for chunk in runner.run(request=request)]
        assert [chunk.kind for chunk in chunks] == ["approval_required"]
        await db_session.commit()

    async with turn_ctx.session() as session:
        row = (
            await session.execute(
                text(
                    "SELECT status, pending_approval FROM session_turns WHERE id = :id"
                ),
                {"id": turn_id},
            )
        ).one()
    assert row[0] == "waiting"
    pending = row[1]
    assert pending["approval_id"] == str(approval_id)
    assert pending["tool_name"] == "danger_tool"
    assert pending["arguments_digest"] == arguments_digest({"path": "/"})
    assert pending["session_id"] == str(session_id)
    assert pending["turn_id"] == str(turn_id)


def _now() -> datetime:
    return datetime.now(UTC)
