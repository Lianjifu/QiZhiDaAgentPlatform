"""``PostgresSessionSweeper`` —— **真库**。

覆盖 Session Stage 1 的清扫落地点（Session 方案 §3.3）：

- **僵尸轮次**（卡在 ``running`` 超过 30 分钟）→ 置 ``failed``；
- **幂等键过期行** → 删掉（**Gateway 的硬依赖**：唯一约束不含
  ``expires_at`` → 过期行留在表里，同一个键重发仍会命中冲突）；
- 没到期的行**不动**。
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from qzdap.modules.agent_runtime.adapter.persistence.idempotency_store import (
    PostgresIdempotencyStore,
)
from qzdap.modules.agent_runtime.adapter.persistence.session_sweeper import (
    PostgresSessionSweeper,
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
CREATE TABLE "{schema}".session_inbox (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    channel_id uuid NOT NULL,
    idempotency_key varchar(255) NOT NULL,
    key_source varchar(32) NOT NULL,
    key_strength varchar(8) NOT NULL DEFAULT 'strong',
    external_message_id varchar(255),
    payload_hash varchar(64),
    status varchar(16) NOT NULL DEFAULT 'claimed',
    claimed_at timestamptz,
    expires_at timestamptz NOT NULL,
    turn_id uuid,
    trace_id varchar(64),
    received_at timestamptz NOT NULL DEFAULT now()
)
""",
]


@pytest.fixture
async def sweeper_ctx():
    url = os.environ.get("QZDAP_TEST_DATABASE_URL")
    if not url:
        pytest.skip("QZDAP_TEST_DATABASE_URL is not set")
    schema = "sweeper_" + uuid.uuid4().hex
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
    sweeper = PostgresSessionSweeper(
        session_factory=factory,
        idempotency_store=PostgresIdempotencyStore(factory),
    )
    try:
        yield sweeper, factory, schema
    finally:
        await engine.dispose()
        async with admin.connect() as conn:
            await conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            await conn.commit()
        await admin.dispose()


async def _insert_turn(factory, *, status: str, started_at: datetime) -> uuid.UUID:
    turn_id = uuid.uuid4()
    async with factory.session() as session, session.begin():
        await session.execute(
            text(
                "INSERT INTO session_turns "
                "(id, tenant_id, workspace_id, session_id, idempotency_key, status, "
                " started_at, agent_version, model_version) "
                "VALUES (:id, :tenant, :ws, :session, :key, :status, :started, 'v1', 'm')"
            ),
            {
                "id": turn_id,
                "tenant": uuid.uuid4(),
                "ws": uuid.uuid4(),
                "session": uuid.uuid4(),
                "key": f"k-{turn_id}",
                "status": status,
                "started": started_at,
            },
        )
    return turn_id


async def _insert_inbox(factory, *, expires_at: datetime) -> uuid.UUID:
    row_id = uuid.uuid4()
    async with factory.session() as session, session.begin():
        await session.execute(
            text(
                "INSERT INTO session_inbox "
                "(id, tenant_id, workspace_id, channel_id, idempotency_key, key_source, "
                " key_strength, status, expires_at) "
                "VALUES (:id, :tenant, :ws, :channel, :key, 'client', 'strong', "
                " 'claimed', :expires)"
            ),
            {
                "id": row_id,
                "tenant": uuid.uuid4(),
                "ws": uuid.uuid4(),
                "channel": uuid.uuid4(),
                "key": f"k-{row_id}",
                "expires": expires_at,
            },
        )
    return row_id


@pytest.mark.asyncio
async def test_a_zombie_turn_is_taken_over(sweeper_ctx) -> None:  # type: ignore[no-untyped-def]
    sweeper, factory, _schema = sweeper_ctx
    stale = await _insert_turn(
        factory,
        status="running",
        started_at=datetime.now(UTC) - timedelta(minutes=45),
    )
    fresh = await _insert_turn(
        factory,
        status="running",
        started_at=datetime.now(UTC) - timedelta(minutes=1),
    )

    report = await sweeper.sweep(now=datetime.now(UTC))
    assert report.zombie_turns == 1

    async with factory.session() as session:
        rows = (
            await session.execute(
                text("SELECT id, status, error_code FROM session_turns ORDER BY id")
            )
        ).all()
    by_id = {row.id: row for row in rows}
    assert by_id[stale].status == "failed"
    assert by_id[stale].error_code == "ZOMBIE_TAKEOVER"
    assert by_id[fresh].status == "running"


@pytest.mark.asyncio
async def test_expired_inbox_rows_are_deleted(sweeper_ctx) -> None:  # type: ignore[no-untyped-def]
    """**Gateway 的硬依赖** —— 过期行不清，表会无限膨胀 ✗。"""
    sweeper, factory, _schema = sweeper_ctx
    expired = await _insert_inbox(
        factory, expires_at=datetime.now(UTC) - timedelta(hours=1)
    )
    alive = await _insert_inbox(
        factory, expires_at=datetime.now(UTC) + timedelta(hours=1)
    )

    report = await sweeper.sweep(now=datetime.now(UTC))
    assert report.expired_idempotency_rows == 1

    async with factory.session() as session:
        rows = (await session.execute(text("SELECT id FROM session_inbox"))).all()
    remaining = {row.id for row in rows}
    assert expired not in remaining
    assert alive in remaining
