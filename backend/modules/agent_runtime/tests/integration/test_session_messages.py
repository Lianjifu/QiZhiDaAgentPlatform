"""会话内两个序列 + 消息双写 —— **真库**。

覆盖 Session Stage 2 的落地点（Session 方案 §5.2）：

- **轮次序**与**消息序**的分配是**原子的**、从 1 开始、单调递增；
- 消息**双写**：新表 ``session_messages`` 与旧表 ``agent_session_messages``
  都有行，且新表的 ``session_seq`` 会话内单调 ✓；
- **跨租户**分配不了别人的会话（租户过滤写进 WHERE ✓）。
"""

from __future__ import annotations

import os
import uuid
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from qzdap.modules.agent_runtime.adapter.persistence.session_messages import (
    PostgresSessionMessageStore,
)
from qzdap.modules.agent_runtime.adapter.persistence.session_sequence import (
    PostgresSessionSequence,
)

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
    next_message_seq integer NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT status_enum CHECK (
        status IN ('open','closed','running','waiting_approval','cancelled')
    )
)
""",
    """
CREATE TABLE "{schema}".session_turns (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    session_id uuid NOT NULL REFERENCES "{schema}".agent_sessions (id) ON DELETE CASCADE,
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
]


@pytest.fixture
async def seq_ctx():
    url = os.environ.get("QZDAP_TEST_DATABASE_URL")
    if not url:
        pytest.skip("QZDAP_TEST_DATABASE_URL is not set")
    schema = "seq_" + uuid.uuid4().hex
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


async def _session(factory, *, tenant_id: UUID) -> tuple[UUID, UUID]:
    """建一个会话行 + 一个轮次行（消息表的外键父行）。"""
    session_id = uuid4()
    turn_id = uuid4()
    async with factory.session() as session, session.begin():
        await session.execute(
            text(
                "INSERT INTO agent_sessions "
                "(id, tenant_id, workspace_id, owner_id, agent_id, agent_version) "
                "VALUES (:id, :tenant, :ws, :owner, :agent, 'v1')"
            ),
            {
                "id": session_id,
                "tenant": tenant_id,
                "ws": uuid4(),
                "owner": uuid4(),
                "agent": uuid4(),
            },
        )
        await session.execute(
            text(
                "INSERT INTO session_turns "
                "(id, tenant_id, workspace_id, session_id, idempotency_key, "
                " agent_version, model_version) "
                "VALUES (:id, :tenant, :ws, :session, :key, 'v1', 'm')"
            ),
            {
                "id": turn_id,
                "tenant": tenant_id,
                "ws": uuid4(),
                "session": session_id,
                "key": f"k-{turn_id}",
            },
        )
    return session_id, turn_id


@pytest.mark.asyncio
async def test_the_two_sequences_are_monotonic_and_start_at_one(seq_ctx) -> None:  # type: ignore[no-untyped-def]
    tenant = uuid4()
    session_id, _turn = await _session(seq_ctx, tenant_id=tenant)

    async with seq_ctx.session() as session:
        sequence = PostgresSessionSequence(session)
        assert (
            await sequence.next_ingress_seq(tenant_id=tenant, session_id=session_id)
            == 1
        )
        assert (
            await sequence.next_ingress_seq(tenant_id=tenant, session_id=session_id)
            == 2
        )
        assert (
            await sequence.next_message_seq(tenant_id=tenant, session_id=session_id)
            == 1
        )
        await session.commit()


@pytest.mark.asyncio
async def test_a_sequence_cannot_be_allocated_across_tenants(seq_ctx) -> None:  # type: ignore[no-untyped-def]
    """租户过滤写进 WHERE —— 别人的会话**分不到号** ✗。"""
    from qzdap.modules.agent_runtime.domain.errors import SessionNotFound

    owner = uuid4()
    session_id, _turn = await _session(seq_ctx, tenant_id=owner)

    async with seq_ctx.session() as session:
        sequence = PostgresSessionSequence(session)
        with pytest.raises(SessionNotFound):
            await sequence.next_ingress_seq(tenant_id=uuid4(), session_id=session_id)


@pytest.mark.asyncio
async def test_messages_are_written_only_to_the_new_table(seq_ctx) -> None:  # type: ignore[no-untyped-def]
    """**只写新表** ✓（旧表停写 S-15b ✓）；``session_seq`` 会话内单调 ✓。"""
    tenant = uuid4()
    session_id, turn_id = await _session(seq_ctx, tenant_id=tenant)

    async with seq_ctx.session() as session:
        store = PostgresSessionMessageStore(session)
        for seq, role, content in ((0, "user", "hello"), (1, "assistant", "hi")):
            await store.append(
                tenant_id=tenant,
                workspace_id=uuid4(),
                session_id=session_id,
                turn_id=turn_id,
                seq=seq,
                role=role,
                content=content,
            )
        await session.commit()

    async with seq_ctx.session() as session:
        new_rows = (
            await session.execute(
                text(
                    "SELECT seq, role, content, session_seq FROM session_messages "
                    "ORDER BY session_seq"
                )
            )
        ).all()
        old_rows = (
            await session.execute(
                text(
                    "SELECT seq, role, content FROM agent_session_messages ORDER BY seq"
                )
            )
        ).all()

    assert [(r.seq, r.role, r.content) for r in new_rows] == [
        (0, "user", "hello"),
        (1, "assistant", "hi"),
    ]
    assert [r.session_seq for r in new_rows] == [1, 2]
    # ⚠️ **旧表不再写** ✓ —— 一行都没有 ✓。
    assert old_rows == []


@pytest.mark.asyncio
async def test_the_session_sequence_is_monotonic_across_turns(seq_ctx) -> None:  # type: ignore[no-untyped-def]
    """跨轮次也单调 —— 上下文重建靠它单表有序扫描 ✓。"""
    tenant = uuid4()
    session_id, turn_id = await _session(seq_ctx, tenant_id=tenant)

    async with seq_ctx.session() as session:
        store = PostgresSessionMessageStore(session)
        await store.append(
            tenant_id=tenant,
            workspace_id=uuid4(),
            session_id=session_id,
            turn_id=turn_id,
            seq=0,
            role="user",
            content="一",
        )
        await store.append(
            tenant_id=tenant,
            workspace_id=uuid4(),
            session_id=session_id,
            turn_id=turn_id,
            seq=1,
            role="assistant",
            content="二",
        )
        await session.commit()

    async with seq_ctx.session() as session:
        rows = (
            await session.execute(
                text("SELECT session_seq FROM session_messages ORDER BY session_seq")
            )
        ).all()
    assert [r.session_seq for r in rows] == [1, 2]


@pytest.mark.asyncio
async def test_reading_comes_from_the_new_table(seq_ctx) -> None:  # type: ignore[no-untyped-def]
    """**切读（S-15a）** —— 读的是**新表** ✓。

    ⚠️ 判据不是「两张表都读得出来」（双写期都一样 ✓，那证明不了什么 ✗）——
    而是**把旧表的行删掉，读仍然有** ✓✓。
    """
    tenant = uuid4()
    session_id, turn_id = await _session(seq_ctx, tenant_id=tenant)

    async with seq_ctx.session() as session:
        store = PostgresSessionMessageStore(session)
        await store.append(
            tenant_id=tenant,
            workspace_id=uuid4(),
            session_id=session_id,
            turn_id=turn_id,
            seq=0,
            role="user",
            content="你好",
        )
        await session.commit()

    # 旧表的行删掉 —— 读**仍然有** ✓（说明读的是新表 ✓）。
    async with seq_ctx.session() as session, session.begin():
        await session.execute(
            text("DELETE FROM agent_session_messages WHERE session_id = :s"),
            {"s": session_id},
        )

    async with seq_ctx.session() as session:
        store = PostgresSessionMessageStore(session)
        rows = await store.list_for_session(session_id)
    assert [row["content"] for row in rows] == ["你好"]
    assert rows[0]["turnId"] == str(turn_id)


@pytest.mark.asyncio
async def test_the_tool_name_survives_in_the_new_table(seq_ctx) -> None:  # type: ignore[no-untyped-def]
    """工具名进 ``metadata_`` ✓ —— 不带上它，切读后工具消息会**丢掉工具名** ✗✗。"""
    tenant = uuid4()
    session_id, turn_id = await _session(seq_ctx, tenant_id=tenant)

    async with seq_ctx.session() as session:
        store = PostgresSessionMessageStore(session)
        await store.append(
            tenant_id=tenant,
            workspace_id=uuid4(),
            session_id=session_id,
            turn_id=turn_id,
            seq=0,
            role="tool",
            content="磁盘已清理",
            tool_name="wipe_disk",
            extra={"duration_ms": 12},
        )
        await session.commit()

    async with seq_ctx.session() as session:
        store = PostgresSessionMessageStore(session)
        rows = await store.list_for_session(session_id)
    assert rows[0]["toolName"] == "wipe_disk"
    assert rows[0]["content"] == "磁盘已清理"


@pytest.mark.asyncio
async def test_the_history_is_ordered_by_session_seq(seq_ctx) -> None:  # type: ignore[no-untyped-def]
    """**按会话内的写入顺序**排 ✓。

    ⚠️ 旧表只能按**轮次内**的 ``seq`` 排 ✗ → 多轮会话的历史会**交错** ✗✗
    （第一轮的第 2 条排在第二轮的第 1 条后面 ✗）。新表有 ``session_seq`` ✓。
    """
    tenant = uuid4()
    session_id, turn_a = await _session(seq_ctx, tenant_id=tenant)
    turn_b = uuid4()
    async with seq_ctx.session() as session, session.begin():
        await session.execute(
            text(
                "INSERT INTO session_turns (id, tenant_id, workspace_id, session_id, "
                " idempotency_key, status, agent_version, model_version) "
                "VALUES (:id, :t, :w, :s, 'k2', 'running', 'v1', 'm')"
            ),
            {
                "id": turn_b,
                "t": tenant,
                "w": uuid4(),
                "s": session_id,
            },
        )

    async with seq_ctx.session() as session:
        store = PostgresSessionMessageStore(session)
        # 第一轮：seq 0 / 1；第二轮：seq 0 —— 两轮的序号会**交错** ✗
        for turn_id, seq, content in (
            (turn_a, 0, "第一轮第一条"),
            (turn_a, 1, "第一轮第二条"),
            (turn_b, 0, "第二轮第一条"),
        ):
            await store.append(
                tenant_id=tenant,
                workspace_id=uuid4(),
                session_id=session_id,
                turn_id=turn_id,
                seq=seq,
                role="user",
                content=content,
            )
        await session.commit()

    async with seq_ctx.session() as session:
        store = PostgresSessionMessageStore(session)
        rows = await store.list_for_session(session_id)
    assert [row["content"] for row in rows] == [
        "第一轮第一条",
        "第一轮第二条",
        "第二轮第一条",
    ]
