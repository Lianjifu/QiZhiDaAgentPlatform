"""``PostgresOutboxRepository`` —— **真库**。

覆盖 Session Stage 4b 的落点（Session 方案 §7 的 outbox）：

- 入队 → 出现在待投递列表 ✓（seq 在轮次内递增 ✓）；
- 投递成功 → 标 delivered → **不再出现在列表里** ✓；
- 投递失败 → 标 failed → **还在列表里**（worker 会重试 ✓）✓；
- 超次数 → **进死信表** ✓（原行删掉 ✓）；
- ⚠️ **chunk 事件不进队列** ✓ —— 那是「事件日志」，不是「待投递的消息」✗
  （混在一起会把 web 的 chunk 投到 IM 渠道 ✗✗）。
"""

from __future__ import annotations

import os
import uuid
from uuid import UUID, uuid4

import pytest
from qzdap_agent_runtime.outbox import IM_REPLY_EVENT_TYPE
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from qzdap.modules.agent_runtime.adapter.persistence.outbox_repository import (
    PostgresOutboxRepository,
)

_DDL = [
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
    cost_usd numeric(12,6),
    expected_revision integer NOT NULL DEFAULT 0,
    error_code varchar(64),
    pending_approval jsonb,
    cancel_requested boolean NOT NULL DEFAULT false,
    ingress_seq integer,
    route_decision jsonb,
    agent_decision jsonb,
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
    PRIMARY KEY (turn_id, seq)
)
""",
    """
CREATE TABLE "{schema}".outbox_dead_letters (
    turn_id uuid NOT NULL,
    seq integer NOT NULL,
    attempt integer NOT NULL,
    event_type varchar(64) NOT NULL,
    payload jsonb NOT NULL,
    last_error text,
    dead_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (turn_id, seq, attempt)
)
""",
]


@pytest.fixture
async def repo_ctx():
    url = os.environ.get("QZDAP_TEST_DATABASE_URL")
    if not url:
        pytest.skip("QZDAP_TEST_DATABASE_URL is not set")
    schema = "outbox_" + uuid.uuid4().hex
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
        yield factory, schema
    finally:
        await engine.dispose()
        async with admin.connect() as conn:
            await conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            await conn.commit()
        await admin.dispose()


async def _turn(factory, schema) -> UUID:
    turn_id = uuid4()
    async with factory.session() as session, session.begin():
        await session.execute(
            text(
                "INSERT INTO session_turns "
                "(id, tenant_id, workspace_id, session_id, idempotency_key, "
                " agent_version, model_version) "
                "VALUES (:id, :t, :w, :s, 'k', 'v1', 'm')"
            ),
            {
                "id": turn_id,
                "t": uuid4(),
                "w": uuid4(),
                "s": uuid4(),
            },
        )
    return turn_id


@pytest.mark.asyncio
async def test_an_enqueued_message_shows_up_in_the_queue(repo_ctx) -> None:  # type: ignore[no-untyped-def]
    factory, _ = repo_ctx
    repo = PostgresOutboxRepository(factory)
    turn_id = await _turn(factory, _)

    outbound = await repo.enqueue(
        turn_id=str(turn_id),
        event_type=IM_REPLY_EVENT_TYPE,
        payload={"content": "你好", "channel_type": "feishu", "chat_id": "c1"},
    )
    pending = await repo.list_pending()
    assert [e.turn_id for e in pending] == [str(turn_id)]
    assert pending[0].seq == outbound.seq
    assert pending[0].payload["content"] == "你好"
    assert pending[0].delivery_attempts == 0


@pytest.mark.asyncio
async def test_a_delivered_message_leaves_the_queue(repo_ctx) -> None:  # type: ignore[no-untyped-def]
    factory, _ = repo_ctx
    repo = PostgresOutboxRepository(factory)
    turn_id = await _turn(factory, _)
    outbound = await repo.enqueue(
        turn_id=str(turn_id), event_type=IM_REPLY_EVENT_TYPE, payload={"content": "hi"}
    )
    await repo.mark_delivered(outbound.turn_id, outbound.seq)
    assert await repo.list_pending() == []


@pytest.mark.asyncio
async def test_a_failed_message_stays_in_the_queue(repo_ctx) -> None:  # type: ignore[no-untyped-def]
    factory, _ = repo_ctx
    repo = PostgresOutboxRepository(factory)
    turn_id = await _turn(factory, _)
    outbound = await repo.enqueue(
        turn_id=str(turn_id), event_type=IM_REPLY_EVENT_TYPE, payload={"content": "hi"}
    )
    await repo.mark_failed(outbound.turn_id, outbound.seq, 1, "network down")
    pending = await repo.list_pending()
    assert len(pending) == 1
    assert pending[0].delivery_status == "failed"
    assert pending[0].delivery_attempts == 1
    assert pending[0].payload["_last_error"] == "network down"


@pytest.mark.asyncio
async def test_a_dead_lettered_message_leaves_the_queue_and_lands_in_the_dead_letters(
    repo_ctx,
) -> None:  # type: ignore[no-untyped-def]
    factory, schema = repo_ctx
    repo = PostgresOutboxRepository(factory)
    turn_id = await _turn(factory, schema)
    outbound = await repo.enqueue(
        turn_id=str(turn_id), event_type=IM_REPLY_EVENT_TYPE, payload={"content": "hi"}
    )
    await repo.move_to_dead_letter(outbound.turn_id, outbound.seq, 8, "gave up")

    assert await repo.list_pending() == []
    async with factory.session() as session:
        row = (
            await session.execute(
                text(
                    "SELECT turn_id, seq, attempt, last_error "
                    "FROM outbox_dead_letters WHERE turn_id = :t"
                ),
                {"t": turn_id},
            )
        ).one()
    assert row[0] == turn_id
    assert row[1] == outbound.seq
    assert row[2] == 8
    assert row[3] == "gave up"


@pytest.mark.asyncio
async def test_the_chunk_events_are_not_in_the_queue(repo_ctx) -> None:  # type: ignore[no-untyped-def]
    """⚠️ chunk 事件是**事件日志**，不是队列 ✓ —— 否则 worker 会把 web 的
    chunk 当成 IM 消息投出去 ✗✗。"""
    factory, schema = repo_ctx
    repo = PostgresOutboxRepository(factory)
    turn_id = await _turn(factory, schema)
    async with factory.session() as session, session.begin():
        await session.execute(
            text(
                "INSERT INTO session_events (turn_id, seq, event_type, payload) "
                "VALUES (:t, 1, 'message', CAST(:p AS jsonb))"
            ),
            {"t": turn_id, "p": '{"content": "hello"}'},
        )
    assert await repo.list_pending() == []


__all__ = []
