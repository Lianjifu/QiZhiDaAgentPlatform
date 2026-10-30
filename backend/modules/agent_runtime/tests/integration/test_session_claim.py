"""会话执行权（互斥）—— **真库**。

覆盖 Session Stage 3 的第一片（台账 R3：``try_claim`` 的会话互斥职责迁到
``current_turn_id`` + ``session_turns.status``）：

- 同一会话**第二个 claim 失败**（互斥 ✓）；
- 不同会话互不干扰；
- release 之后可以再 claim；
- **僵尸轮次**（running 但超过 30 分钟）可以被接管 ✓；
- 已到终态的轮次可以被接管 ✓；
- **跨租户** claim 不了别人的会话 ✓。
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from qzdap_agent_runtime.session.state import TurnStatus
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from qzdap.modules.agent_runtime.adapter.persistence.session_claim import (
    PostgresTurnClaim,
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
]


@pytest.fixture
async def claim_ctx():
    url = os.environ.get("QZDAP_TEST_DATABASE_URL")
    if not url:
        pytest.skip("QZDAP_TEST_DATABASE_URL is not set")
    schema = "claim_" + uuid.uuid4().hex
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


async def _session(factory, *, tenant_id: UUID) -> UUID:
    session_id = uuid4()
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
    return session_id


async def _turn(
    factory,
    *,
    session_id: UUID,
    status: str = "running",
    started_at: datetime | None = None,
) -> UUID:
    turn_id = uuid4()
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
                "tenant": uuid4(),
                "ws": uuid4(),
                "session": session_id,
                "key": f"k-{turn_id}",
                "status": status,
                "started": started_at or datetime.now(UTC),
            },
        )
    return turn_id


async def _bind(factory, *, session_id: UUID, turn_id: UUID) -> None:
    """把会话的 ``current_turn_id`` 指到某个轮次（模拟「这一轮在飞」）。"""
    async with factory.session() as session, session.begin():
        await session.execute(
            text("UPDATE agent_sessions SET current_turn_id = :turn WHERE id = :sid"),
            {"turn": turn_id, "sid": session_id},
        )


@pytest.mark.asyncio
async def test_only_one_turn_can_hold_a_session(claim_ctx) -> None:  # type: ignore[no-untyped-def]
    tenant = uuid4()
    session_id = await _session(claim_ctx, tenant_id=tenant)

    async with claim_ctx.session() as session:
        claim = PostgresTurnClaim(session)
        assert await claim.claim(
            tenant_id=tenant, session_id=session_id, turn_id=uuid4()
        )
        # 第二个 claim 必须失败 —— 否则两轮的消息会交错 ✗
        assert not await claim.claim(
            tenant_id=tenant, session_id=session_id, turn_id=uuid4()
        )


@pytest.mark.asyncio
async def test_different_sessions_do_not_block_each_other(claim_ctx) -> None:  # type: ignore[no-untyped-def]
    tenant = uuid4()
    a = await _session(claim_ctx, tenant_id=tenant)
    b = await _session(claim_ctx, tenant_id=tenant)

    async with claim_ctx.session() as session:
        claim = PostgresTurnClaim(session)
        assert await claim.claim(tenant_id=tenant, session_id=a, turn_id=uuid4())
        assert await claim.claim(tenant_id=tenant, session_id=b, turn_id=uuid4())


@pytest.mark.asyncio
async def test_releasing_frees_the_session(claim_ctx) -> None:  # type: ignore[no-untyped-def]
    tenant = uuid4()
    session_id = await _session(claim_ctx, tenant_id=tenant)
    turn_id = uuid4()

    async with claim_ctx.session() as session:
        claim = PostgresTurnClaim(session)
        assert await claim.claim(
            tenant_id=tenant, session_id=session_id, turn_id=turn_id
        )
        await claim.release(tenant_id=tenant, session_id=session_id, turn_id=turn_id)
        assert await claim.claim(
            tenant_id=tenant, session_id=session_id, turn_id=uuid4()
        )


@pytest.mark.asyncio
async def test_a_zombie_turn_can_be_taken_over(claim_ctx) -> None:  # type: ignore[no-untyped-def]
    """上一轮异常退出（轮次永远 running）→ 超过阈值就能接管 ✓。"""
    tenant = uuid4()
    session_id = await _session(claim_ctx, tenant_id=tenant)
    zombie = await _turn(
        claim_ctx,
        session_id=session_id,
        status="running",
        started_at=datetime.now(UTC) - timedelta(minutes=45),
    )
    await _bind(claim_ctx, session_id=session_id, turn_id=zombie)

    async with claim_ctx.session() as session:
        claim = PostgresTurnClaim(session)
        assert await claim.claim(
            tenant_id=tenant, session_id=session_id, turn_id=uuid4()
        )


@pytest.mark.asyncio
async def test_a_finished_turn_does_not_block_the_session(claim_ctx) -> None:  # type: ignore[no-untyped-def]
    """轮次已到终态 —— 会话可以开下一轮 ✓（``current_turn_id`` 没清干净也
    自愈 ✓）。"""
    tenant = uuid4()
    session_id = await _session(claim_ctx, tenant_id=tenant)
    done = await _turn(claim_ctx, session_id=session_id, status="succeeded")
    await _bind(claim_ctx, session_id=session_id, turn_id=done)

    async with claim_ctx.session() as session:
        claim = PostgresTurnClaim(session)
        assert await claim.claim(
            tenant_id=tenant, session_id=session_id, turn_id=uuid4()
        )


@pytest.mark.asyncio
async def test_another_tenant_cannot_claim_the_session(claim_ctx) -> None:  # type: ignore[no-untyped-def]
    owner = uuid4()
    session_id = await _session(claim_ctx, tenant_id=owner)

    async with claim_ctx.session() as session:
        claim = PostgresTurnClaim(session)
        assert not await claim.claim(
            tenant_id=uuid4(), session_id=session_id, turn_id=uuid4()
        )


@pytest.mark.asyncio
async def test_the_current_turn_status_is_reported(claim_ctx) -> None:  # type: ignore[no-untyped-def]
    tenant = uuid4()
    session_id = await _session(claim_ctx, tenant_id=tenant)
    turn_id = await _turn(claim_ctx, session_id=session_id, status="waiting")
    await _bind(claim_ctx, session_id=session_id, turn_id=turn_id)

    async with claim_ctx.session() as session:
        claim = PostgresTurnClaim(session)
        assert (
            await claim.current_turn_status(tenant_id=tenant, session_id=session_id)
            is TurnStatus.WAITING
        )
