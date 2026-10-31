"""``PostgresTurnQueue`` —— **真库** ✓（Router Stage 3 的落地点 ✓）。

覆盖 Router 方案 §4.2 的三个机制 ✓：

- **入队** ✓（轮次行 ``status='queued'`` ✓）；
- **FIFO 放行** ✓（``ingress_seq == last_completed_seq + 1`` ✓）；
- **兜底路径** ✓（快照落后 → **以权威值为准放行** ✓ + **修快照** ✓）。

⚠️ **互斥只有一个权威** ✓（决策 #9 ✓）—— 轮次行的状态 CAS ✓。
"""

from __future__ import annotations

import os
import uuid
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from qzdap.modules.agent_runtime.adapter.persistence.session_queue import (
    PostgresTurnQueue,
)

_DDL = [
    """
CREATE TABLE "{schema}".agent_sessions (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    status varchar(32) NOT NULL DEFAULT 'open',
    current_turn_id uuid,
    next_ingress_seq integer NOT NULL DEFAULT 0,
    last_completed_seq integer NOT NULL DEFAULT 0,
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
    user_input text,
    status varchar(16) NOT NULL DEFAULT 'running',
    started_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    trace_id varchar(64),
    agent_version varchar(64) NOT NULL,
    model_version varchar(64) NOT NULL,
    cost_usd numeric(12, 6),
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
CREATE UNIQUE INDEX uq_session_turns_session_ingress_seq
    ON "{schema}".session_turns (session_id, ingress_seq)
    WHERE ingress_seq IS NOT NULL
""",
]


@pytest.fixture
async def queue_ctx():
    url = os.environ.get("QZDAP_TEST_DATABASE_URL")
    if not url:
        pytest.skip("QZDAP_TEST_DATABASE_URL is not set")
    schema = "queue_" + uuid.uuid4().hex
    admin = create_async_engine(url)
    async with admin.connect() as conn:
        await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        for statement in _DDL:
            await conn.execute(text(statement.replace("{schema}", schema)))
        await conn.commit()

    engine = create_async_engine(url, connect_args={"server_settings": {"search_path": schema}})
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


async def _seed_session(session, *, session_id, tenant_id, workspace_id) -> None:
    await session.execute(
        text(
            "INSERT INTO agent_sessions (id, tenant_id, workspace_id) "
            "VALUES (:id, :tenant, :workspace)"
        ),
        {"id": session_id, "tenant": tenant_id, "workspace": workspace_id},
    )


async def _seed_turn(
    session, *, turn_id, session_id, tenant_id, workspace_id, ingress_seq, status
) -> None:
    await session.execute(
        text(
            "INSERT INTO session_turns (id, tenant_id, workspace_id, session_id, "
            "idempotency_key, agent_version, model_version, status, ingress_seq) "
            "VALUES (:id, :tenant, :workspace, :session, :key, 'v1', 'm1', "
            ":status, :ingress_seq)"
        ),
        {
            "id": turn_id,
            "tenant": tenant_id,
            "workspace": workspace_id,
            "session": session_id,
            "key": uuid4().hex,
            "status": status,
            "ingress_seq": ingress_seq,
        },
    )


async def _advance_snapshot(session, *, session_id, tenant_id, value) -> None:
    await session.execute(
        text(
            "UPDATE agent_sessions SET last_completed_seq = :value "
            "WHERE id = :session AND tenant_id = :tenant"
        ),
        {"value": value, "session": session_id, "tenant": tenant_id},
    )


@pytest.mark.asyncio
async def test_the_next_turn_is_released_and_the_later_one_waits(queue_ctx) -> None:  # type: ignore[no-untyped-def]
    """**FIFO 放行** ✓ —— 轮到的那个能跑 ✓，后面的等 ✓。"""
    tenant, workspace, session_id = uuid4(), uuid4(), uuid4()
    first, second = uuid4(), uuid4()
    async with queue_ctx.session() as session, session.begin():
        await _seed_session(
            session,
            session_id=session_id,
            tenant_id=tenant,
            workspace_id=workspace,
        )
        await _seed_turn(
            session,
            turn_id=first,
            session_id=session_id,
            tenant_id=tenant,
            workspace_id=workspace,
            ingress_seq=1,
            status="queued",
        )
        await _seed_turn(
            session,
            turn_id=second,
            session_id=session_id,
            tenant_id=tenant,
            workspace_id=workspace,
            ingress_seq=2,
            status="queued",
        )
        queue = PostgresTurnQueue(session)

        # ⚠️ **轮到的那个放行** ✓（快照 = 0 → 放行 ingress_seq=1 ✓）。
        decision = await queue.try_release(
            tenant_id=tenant,
            session_id=session_id,
            turn_id=first,
            ingress_seq=1,
        )
        assert decision.outcome == "released"

        # ⚠️ **后面的那个继续等** ✓（会话里已经有 running 的轮次 ✓）。
        blocked = await queue.try_release(
            tenant_id=tenant,
            session_id=session_id,
            turn_id=second,
            ingress_seq=2,
        )
        assert blocked.outcome == "waiting"
        assert blocked.position == 1


@pytest.mark.asyncio
async def test_the_next_turn_is_released_after_the_previous_one_finished(queue_ctx) -> None:  # type: ignore[no-untyped-def]
    """**上一轮结束 → 下一轮放行** ✓。"""
    tenant, workspace, session_id = uuid4(), uuid4(), uuid4()
    first, second = uuid4(), uuid4()
    async with queue_ctx.session() as session, session.begin():
        await _seed_session(
            session,
            session_id=session_id,
            tenant_id=tenant,
            workspace_id=workspace,
        )
        await _seed_turn(
            session,
            turn_id=first,
            session_id=session_id,
            tenant_id=tenant,
            workspace_id=workspace,
            ingress_seq=1,
            status="succeeded",
        )
        await _seed_turn(
            session,
            turn_id=second,
            session_id=session_id,
            tenant_id=tenant,
            workspace_id=workspace,
            ingress_seq=2,
            status="queued",
        )
        await _advance_snapshot(session, session_id=session_id, tenant_id=tenant, value=1)
        queue = PostgresTurnQueue(session)
        decision = await queue.try_release(
            tenant_id=tenant,
            session_id=session_id,
            turn_id=second,
            ingress_seq=2,
        )
        assert decision.outcome == "released"


@pytest.mark.asyncio
async def test_the_stale_snapshot_falls_back_to_the_authority(queue_ctx) -> None:  # type: ignore[no-untyped-def]
    """**快照落后 → 兜底放行** ✓（Router 方案 §4.2 ✓ —— 否则队列卡死 ✗✗）。"""
    tenant, workspace, session_id = uuid4(), uuid4(), uuid4()
    first, second = uuid4(), uuid4()
    async with queue_ctx.session() as session, session.begin():
        await _seed_session(
            session,
            session_id=session_id,
            tenant_id=tenant,
            workspace_id=workspace,
        )
        await _seed_turn(
            session,
            turn_id=first,
            session_id=session_id,
            tenant_id=tenant,
            workspace_id=workspace,
            ingress_seq=1,
            status="succeeded",
        )
        await _seed_turn(
            session,
            turn_id=second,
            session_id=session_id,
            tenant_id=tenant,
            workspace_id=workspace,
            ingress_seq=2,
            status="queued",
        )
        # ⚠️ **快照落后** ✓（还是 0 ✓ —— 上一轮已 succeeded ✓ 但快照没跟上 ✓）。
        queue = PostgresTurnQueue(session)
        decision = await queue.try_release(
            tenant_id=tenant,
            session_id=session_id,
            turn_id=second,
            ingress_seq=2,
        )
        assert decision.outcome == "released"
        # ⚠️ **快照被修好了** ✓（兜底路径的副作用 ✓）。
        row = await session.execute(
            text(
                "SELECT last_completed_seq FROM agent_sessions "
                "WHERE id = :session AND tenant_id = :tenant"
            ),
            {"session": session_id, "tenant": tenant},
        )
        assert int(row.scalar_one()) == 1


@pytest.mark.asyncio
async def test_the_queue_depth_and_position_are_reported(queue_ctx) -> None:  # type: ignore[no-untyped-def]
    """**队列深度与位置** ✓（上限与「我排第几个」的判据 ✓）。"""
    tenant, workspace, session_id = uuid4(), uuid4(), uuid4()
    async with queue_ctx.session() as session, session.begin():
        await _seed_session(
            session,
            session_id=session_id,
            tenant_id=tenant,
            workspace_id=workspace,
        )
        for seq in (1, 2, 3):
            await _seed_turn(
                session,
                turn_id=uuid4(),
                session_id=session_id,
                tenant_id=tenant,
                workspace_id=workspace,
                ingress_seq=seq,
                status="queued",
            )
        queue = PostgresTurnQueue(session)
        assert await queue.queue_depth(tenant_id=tenant, session_id=session_id) == 3
        assert (
            await queue.queue_position(tenant_id=tenant, session_id=session_id, ingress_seq=2) == 2
        )
