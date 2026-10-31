"""上下文清单落库 —— **真库**。

覆盖 Context Stage 3（Persistence）：

- manifest 按 ``(turn_id, step)`` 落库 ✓（每次模型调用一条 ✓）；
- **同一个 step 落两次会报错** ✓（冲突即 bug ✓ —— 不静默覆盖 ✗✗）；
- 摘要写进新列 ``agent_sessions.rolling_summary`` ✓；
- 跨租户写摘要**写不到**别人的会话 ✓。
"""

from __future__ import annotations

import os
import uuid
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from qzdap.modules.agent_runtime.adapter.persistence.context_manifest_store import (
    PostgresContextManifestStore,
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
    rolling_summary text NOT NULL DEFAULT '',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
)
""",
    """
CREATE TABLE "{schema}".session_context_manifests (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    session_id uuid NOT NULL,
    turn_id uuid NOT NULL,
    step integer NOT NULL,
    manifest jsonb NOT NULL,
    tokens_total integer NOT NULL DEFAULT 0,
    degraded jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_session_context_manifests_turn_step UNIQUE (turn_id, step)
)
""",
]


@pytest.fixture
async def manifest_ctx():
    url = os.environ.get("QZDAP_TEST_DATABASE_URL")
    if not url:
        pytest.skip("QZDAP_TEST_DATABASE_URL is not set")
    schema = "ctxman_" + uuid.uuid4().hex
    admin = create_async_engine(url)
    async with admin.connect() as conn:
        await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        for statement in _DDL:
            await conn.execute(text(statement.replace("{schema}", schema)))
        await conn.commit()

    engine = create_async_engine(url, connect_args={"server_settings": {"search_path": schema}})
    try:
        yield engine, schema
    finally:
        await engine.dispose()
        async with admin.connect() as conn:
            await conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            await conn.commit()
        await admin.dispose()


async def _session_row(engine, *, session_id: UUID, tenant_id: UUID) -> None:
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO agent_sessions (id, tenant_id, workspace_id, owner_id, "
                " agent_id, agent_version) "
                "VALUES (:id, :tenant_id, :ws, :owner, :agent, 'v1')"
            ),
            {
                "id": session_id,
                "tenant_id": tenant_id,
                "ws": uuid4(),
                "owner": uuid4(),
                "agent": uuid4(),
            },
        )


@pytest.mark.asyncio
async def test_a_manifest_row_lands_with_its_contents(manifest_ctx) -> None:  # type: ignore[no-untyped-def]
    engine, _schema = manifest_ctx
    tenant = uuid4()
    session_id, turn_id = uuid4(), uuid4()
    await _session_row(engine, session_id=session_id, tenant_id=tenant)

    async with AsyncSession(engine) as session, session.begin():
        store = PostgresContextManifestStore(session)
        await store.save_manifest(
            tenant_id=tenant,
            workspace_id=uuid4(),
            session_id=session_id,
            turn_id=turn_id,
            step=0,
            manifest={"entries": [{"source": "system", "tokens": 12}]},
            tokens_total=12,
            degraded={"recall_degraded": False},
        )

    async with engine.connect() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT manifest, tokens_total, degraded FROM "
                    "session_context_manifests WHERE turn_id = :turn_id AND step = 0"
                ),
                {"turn_id": turn_id},
            )
        ).one()
    assert row[0]["entries"][0]["source"] == "system"
    assert row[1] == 12
    assert row[2] == {"recall_degraded": False}


@pytest.mark.asyncio
async def test_the_same_step_twice_is_a_bug(manifest_ctx) -> None:  # type: ignore[no-untyped-def]
    """同一个 ``(turn_id, step)`` 落两次 → **报错** ✓（不静默覆盖 ✗✗）。"""
    engine, _schema = manifest_ctx
    tenant = uuid4()
    session_id, turn_id = uuid4(), uuid4()
    await _session_row(engine, session_id=session_id, tenant_id=tenant)

    async with AsyncSession(engine) as session, session.begin():
        store = PostgresContextManifestStore(session)
        # 第一次落库正常 ✓
        await store.save_manifest(
            tenant_id=tenant,
            workspace_id=uuid4(),
            session_id=session_id,
            turn_id=turn_id,
            step=0,
            manifest={"entries": []},
            tokens_total=0,
        )
        # 同一个 (turn_id, step) 再落一次 → **报错** ✓
        with pytest.raises(RuntimeError):
            await store.save_manifest(
                tenant_id=tenant,
                workspace_id=uuid4(),
                session_id=session_id,
                turn_id=turn_id,
                step=0,
                manifest={"entries": []},
                tokens_total=0,
            )


@pytest.mark.asyncio
async def test_a_different_step_is_a_different_row(manifest_ctx) -> None:  # type: ignore[no-untyped-def]
    """ReAct 一轮里**多次模型调用** → 多个 step ✓（决策 #6 ✓）。"""
    engine, _schema = manifest_ctx
    tenant = uuid4()
    session_id, turn_id = uuid4(), uuid4()
    await _session_row(engine, session_id=session_id, tenant_id=tenant)

    async with AsyncSession(engine) as session, session.begin():
        store = PostgresContextManifestStore(session)
        for step in (0, 1, 2):
            await store.save_manifest(
                tenant_id=tenant,
                workspace_id=uuid4(),
                session_id=session_id,
                turn_id=turn_id,
                step=step,
                manifest={"entries": []},
                tokens_total=step,
            )

    async with engine.connect() as conn:
        count = (
            await conn.execute(
                text("SELECT count(*) FROM session_context_manifests WHERE turn_id = :t"),
                {"t": turn_id},
            )
        ).scalar_one()
    assert count == 3


@pytest.mark.asyncio
async def test_the_rolling_summary_lands_in_the_new_column(manifest_ctx) -> None:  # type: ignore[no-untyped-def]
    engine, _schema = manifest_ctx
    tenant = uuid4()
    session_id = uuid4()
    await _session_row(engine, session_id=session_id, tenant_id=tenant)

    async with AsyncSession(engine) as session, session.begin():
        store = PostgresContextManifestStore(session)
        await store.save_rolling_summary(
            tenant_id=tenant, session_id=session_id, summary="此前的结论"
        )

    async with engine.connect() as conn:
        value = (
            await conn.execute(
                text("SELECT rolling_summary FROM agent_sessions WHERE id = :id"),
                {"id": session_id},
            )
        ).scalar_one()
    assert value == "此前的结论"


@pytest.mark.asyncio
async def test_another_tenant_cannot_write_the_summary(manifest_ctx) -> None:  # type: ignore[no-untyped-def]
    engine, _schema = manifest_ctx
    tenant, other = uuid4(), uuid4()
    session_id = uuid4()
    await _session_row(engine, session_id=session_id, tenant_id=tenant)

    async with AsyncSession(engine) as session, session.begin():
        store = PostgresContextManifestStore(session)
        await store.save_rolling_summary(tenant_id=other, session_id=session_id, summary="越权写入")

    async with engine.connect() as conn:
        value = (
            await conn.execute(
                text("SELECT rolling_summary FROM agent_sessions WHERE id = :id"),
                {"id": session_id},
            )
        ).scalar_one()
    assert value == ""
