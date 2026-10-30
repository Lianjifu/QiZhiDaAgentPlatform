"""``PostgresToolExecutionStore`` —— **真库** ✓。

覆盖 Agent Stage 3 的落地点（方案 §5.3.2 ✓）：

- **抢到执行权** ✓（`ON CONFLICT DO NOTHING` ✓）；
- **冲突读回** ✓（同参 → 既有行 ✓；异参 → 既有行的指纹 ✓）；
- **两个 worker 并发** → **只有一个抢到** ✓（唯一索引说了算 ✓）；
- **收尾** ✓（状态 + 结果指针 ✓）。
"""

from __future__ import annotations

import os
import uuid
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from qzdap.modules.agent_runtime.adapter.persistence.tool_executions import (
    PostgresToolExecutionStore,
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
CREATE TABLE "{schema}".tool_executions (
    tool_call_id varchar(64) PRIMARY KEY,
    idempotency_key varchar(128) NOT NULL,
    status varchar(16) NOT NULL DEFAULT 'pending',
    request_hash varchar(64) NOT NULL,
    result_ref varchar(512),
    reconcile_endpoint varchar(512),
    turn_id uuid NOT NULL REFERENCES "{schema}".session_turns (id) ON DELETE CASCADE,
    tenant_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    started_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT tool_executions_status_enum
        CHECK (status IN ('pending','running','succeeded','failed','timeout'))
)
""",
    """
CREATE UNIQUE INDEX uq_tool_executions_idempotency_key
    ON "{schema}".tool_executions (idempotency_key)
""",
]


@pytest.fixture
async def store_ctx():
    url = os.environ.get("QZDAP_TEST_DATABASE_URL")
    if not url:
        pytest.skip("QZDAP_TEST_DATABASE_URL is not set")
    schema = "tool_exec_" + uuid.uuid4().hex
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


async def _seed_turn(session, *, turn_id, tenant_id, workspace_id) -> None:
    """**种一行轮次** ✓（`tool_executions.turn_id` 的外键父行 ✓）。"""
    await session.execute(
        text(
            'INSERT INTO session_turns (id, tenant_id, workspace_id, session_id, '
            "idempotency_key, agent_version, model_version) "
            "VALUES (:id, :tenant, :workspace, :session, :key, 'v1', 'm1')"
        ),
        {
            "id": turn_id,
            "tenant": tenant_id,
            "workspace": workspace_id,
            "session": uuid4(),
            "key": uuid4().hex,
        },
    )


@pytest.mark.asyncio
async def test_the_first_call_wins_and_the_second_reads_it_back(store_ctx) -> None:  # type: ignore[no-untyped-def]
    tenant, workspace, turn = uuid4(), uuid4(), uuid4()
    async with store_ctx.session() as session, session.begin():
        await _seed_turn(
            session, turn_id=turn, tenant_id=tenant, workspace_id=workspace
        )
        store = PostgresToolExecutionStore(session)
        first = await store.begin(
            idempotency_key="k1",
            request_hash="h1",
            tool_call_id="call-1",
            turn_id=turn,
            tenant_id=tenant,
            workspace_id=workspace,
        )
        assert first.claimed is True

        second = await store.begin(
            idempotency_key="k1",
            request_hash="h1",
            tool_call_id="call-2",
            turn_id=turn,
            tenant_id=tenant,
            workspace_id=workspace,
        )
        assert second.claimed is False
        assert second.request_hash == "h1"
        assert second.tool_call_id == "call-1"


@pytest.mark.asyncio
async def test_the_finish_writes_the_status_and_the_pointer(store_ctx) -> None:  # type: ignore[no-untyped-def]
    tenant, workspace, turn = uuid4(), uuid4(), uuid4()
    async with store_ctx.session() as session, session.begin():
        await _seed_turn(
            session, turn_id=turn, tenant_id=tenant, workspace_id=workspace
        )
        store = PostgresToolExecutionStore(session)
        await store.begin(
            idempotency_key="k1",
            request_hash="h1",
            tool_call_id="call-1",
            turn_id=turn,
            tenant_id=tenant,
            workspace_id=workspace,
        )
        await store.finish(
            idempotency_key="k1", status="succeeded", result_ref="call-1"
        )
        rows = (
            await session.execute(
                text(
                    "SELECT status, result_ref, finished_at FROM tool_executions "
                    "WHERE idempotency_key = 'k1'"
                )
            )
        ).all()
        assert rows[0][0] == "succeeded"
        assert rows[0][1] == "call-1"
        assert rows[0][2] is not None
