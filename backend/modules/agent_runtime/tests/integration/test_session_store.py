"""``PostgresSessionStore`` —— **真库**。

覆盖 Session Stage 1 的落地点（Session 方案 §3.1）：

- 建会话 → 按 ``channel_session_key`` 查得到；
- **并发创建靠唯一约束**（迁移 0046 的**部分**唯一索引）—— 同租户同 key
  第二次插入返回 ``None``，**不是报错**；
- 不同租户同 key **互不干扰**；
- 关闭 / 归档的语义（终态 + 幂等）。
"""

from __future__ import annotations

import os
import uuid
from uuid import UUID, uuid4

import pytest
from qzdap_agent_runtime.session.manager import (
    AgentBinding,
    CloseReason,
    SessionIdentity,
)
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from qzdap.modules.agent_runtime.adapter.persistence.session_store import (
    PostgresSessionStore,
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
    next_message_seq integer NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT status_enum CHECK (
        status IN ('open','closed','running','waiting_approval','cancelled')
    )
)
""",
    """
CREATE UNIQUE INDEX uq_agent_sessions_channel_key
    ON "{schema}".agent_sessions (tenant_id, channel_session_key)
    WHERE channel_session_key IS NOT NULL
""",
]


@pytest.fixture
async def store_ctx():
    url = os.environ.get("QZDAP_TEST_DATABASE_URL")
    if not url:
        pytest.skip("QZDAP_TEST_DATABASE_URL is not set")
    schema = "session_store_" + uuid.uuid4().hex
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


def _identity(*, tenant_id: UUID, key: str) -> SessionIdentity:
    return SessionIdentity(
        tenant_id=tenant_id,
        workspace_id=uuid4(),
        owner_id=uuid4(),
        channel_session_key=key,
        metadata={"origin": "test"},
    )


def _binding() -> AgentBinding:
    return AgentBinding(agent_id=uuid4(), agent_version="v1")


@pytest.mark.asyncio
async def test_a_new_session_is_found_by_its_channel_key(store_ctx) -> None:  # type: ignore[no-untyped-def]
    tenant = uuid4()
    async with store_ctx.session() as session, session.begin():
        store = PostgresSessionStore(session)
        created = await store.insert_session(
            identity=_identity(tenant_id=tenant, key="k1"), agent=_binding()
        )
        assert created is not None

        found = await store.find_by_channel_key(
            tenant_id=tenant, channel_session_key="k1"
        )
        assert found is not None
        assert found.tenant_id == tenant
        assert found.session_id == created
        assert found.status.value == "open"


@pytest.mark.asyncio
async def test_a_second_insert_with_the_same_key_conflicts(store_ctx) -> None:  # type: ignore[no-untyped-def]
    """**唯一约束**兜住并发创建 —— 冲突返回 ``None``，不是抛异常 ✓。"""
    tenant = uuid4()
    async with store_ctx.session() as session, session.begin():
        store = PostgresSessionStore(session)
        first = await store.insert_session(
            identity=_identity(tenant_id=tenant, key="k1"), agent=_binding()
        )
        second = await store.insert_session(
            identity=_identity(tenant_id=tenant, key="k1"), agent=_binding()
        )
        assert first is not None
        assert second is None


@pytest.mark.asyncio
async def test_the_same_key_in_another_tenant_is_a_different_session(store_ctx) -> None:  # type: ignore[no-untyped-def]
    async with store_ctx.session() as session, session.begin():
        store = PostgresSessionStore(session)
        a = await store.insert_session(
            identity=_identity(tenant_id=uuid4(), key="k1"), agent=_binding()
        )
        b = await store.insert_session(
            identity=_identity(tenant_id=uuid4(), key="k1"), agent=_binding()
        )
        assert a is not None and b is not None
        assert a != b


@pytest.mark.asyncio
async def test_an_unknown_key_is_not_found(store_ctx) -> None:  # type: ignore[no-untyped-def]
    async with store_ctx.session() as session, session.begin():
        store = PostgresSessionStore(session)
        assert (
            await store.find_by_channel_key(
                tenant_id=uuid4(), channel_session_key="nope"
            )
            is None
        )


@pytest.mark.asyncio
async def test_closing_is_terminal_and_idempotent(store_ctx) -> None:  # type: ignore[no-untyped-def]
    tenant = uuid4()
    async with store_ctx.session() as session, session.begin():
        store = PostgresSessionStore(session)
        created = await store.insert_session(
            identity=_identity(tenant_id=tenant, key="k1"), agent=_binding()
        )
        assert created is not None

    async with store_ctx.session() as session:
        store = PostgresSessionStore(session)
        await store.close_session(
            session_id=created, tenant_id=tenant, reason=CloseReason.USER
        )
        await store.close_session(
            session_id=created, tenant_id=tenant, reason=CloseReason.USER
        )
        found = await store.find_by_channel_key(
            tenant_id=tenant, channel_session_key="k1"
        )
        assert found is not None
        assert found.status.value == "closed"


@pytest.mark.asyncio
async def test_archiving_marks_the_metadata_and_closes(store_ctx) -> None:  # type: ignore[no-untyped-def]
    tenant = uuid4()
    async with store_ctx.session() as session, session.begin():
        store = PostgresSessionStore(session)
        created = await store.insert_session(
            identity=_identity(tenant_id=tenant, key="k1"), agent=_binding()
        )
        assert created is not None

    async with store_ctx.session() as session:
        store = PostgresSessionStore(session)
        await store.archive_session(session_id=created, tenant_id=tenant)

    async with store_ctx.session() as session:
        rows = (
            await session.execute(
                text("SELECT status, metadata FROM agent_sessions WHERE id = :id"),
                {"id": created},
            )
        ).one()
        assert rows[0] == "closed"
        assert rows[1]["archived"] is True
        assert rows[1]["origin"] == "test"
