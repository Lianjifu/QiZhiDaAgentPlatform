"""迁移 0054（旧表 → 新表的数据迁移）—— **真库** ✓。

覆盖 Session Stage 6 的「迁数据」那半：

- 历史轮次从 ``agent_turns`` 补进 ``session_turns`` ✓（键带 ``legacy:`` 前缀 ✓）；
- 历史消息从 ``agent_session_messages`` 补进 ``session_messages`` ✓；
- **会话内序号重新编号** ✓（历史在前 ✓）且连续 ✓；
- 计数器 ``next_message_seq`` 跟着走 ✓；
- ⚠️ **挂不上轮次的消息搬不动** ✓（新表外键指向 ``session_turns`` ✗）——
  搬不动的那些**必须被对账脚本报出来** ✓（切读前处理掉 ✗）；
- downgrade 能把回填进来的行**删干净** ✓。
"""

from __future__ import annotations

import importlib.util
import os
import uuid
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from qzdap.modules.agent_runtime.adapter.persistence.models import (
    SessionMessageORM,
    SessionORM,
    SessionTurnORM,
)

#: 旧表的样子 —— ORM 已删（停旧写 ✓），但**表还在**（到 Stage 6 的 S-36 才
#: DROP ✓）→ 测试里用裸 DDL 造出来 ✓（形状照抄真实表 ✓）。
_LEGACY_DDL = [
    """
CREATE TABLE agent_turns (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    session_id uuid NOT NULL REFERENCES agent_sessions (id) ON DELETE CASCADE,
    user_input text NOT NULL,
    started_at timestamptz NOT NULL DEFAULT now(),
    status varchar(16) NOT NULL DEFAULT 'running',
    finished_at timestamptz,
    final_response text,
    error_code varchar(64),
    input_tokens integer,
    output_tokens integer,
    cost_usd double precision,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT status_enum CHECK (status IN ('running','succeeded','failed','denied'))
)
""",
    """
CREATE TABLE agent_session_messages (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    session_id uuid NOT NULL,
    turn_id uuid,
    seq integer NOT NULL DEFAULT 0,
    role varchar(32) NOT NULL,
    content text NOT NULL DEFAULT '',
    tool_name varchar(128) NOT NULL DEFAULT '',
    extra jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
)
""",
]

_MIGRATION = (
    Path(__file__).resolve().parents[4] / "migrations/versions/0054_session_legacy_backfill.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("m0054_test", _MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
async def db_ctx():
    url = os.environ.get("QZDAP_TEST_DATABASE_URL")
    if not url:
        pytest.skip("QZDAP_TEST_DATABASE_URL is not set")
    schema = "backfill_" + uuid.uuid4().hex
    admin = create_async_engine(url)
    async with admin.connect() as conn:
        await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
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


async def _prepare(engine) -> dict:
    """建表 + 造历史数据 ✓（旧表有数据、新表基本是空的 ✓）。"""
    tenant = uuid4()
    workspace = uuid4()
    owner = uuid4()
    agent = uuid4()
    s1, s2 = uuid4(), uuid4()
    t1, t2, t3 = uuid4(), uuid4(), uuid4()
    async with engine.begin() as conn:
        for model in (
            SessionORM,
            SessionTurnORM,
            SessionMessageORM,
        ):
            await conn.run_sync(model.__table__.create)
        for statement in _LEGACY_DDL:
            await conn.execute(text(statement))
        await conn.execute(
            SessionORM.__table__.insert(),
            [
                {
                    "id": s1,
                    "tenant_id": tenant,
                    "workspace_id": workspace,
                    "owner_id": owner,
                    "agent_id": agent,
                    "agent_version": "v1",
                    "status": "open",
                    "metadata": {},
                    "graph_state": {},
                },
                {
                    "id": s2,
                    "tenant_id": tenant,
                    "workspace_id": workspace,
                    "owner_id": owner,
                    "agent_id": agent,
                    "agent_version": "v1",
                    "status": "open",
                    "metadata": {},
                    "graph_state": {},
                },
            ],
        )
        await conn.execute(
            text(
                "INSERT INTO agent_turns (id, tenant_id, workspace_id, session_id, "
                " user_input, status, started_at, finished_at, cost_usd) "
                "VALUES (:id, :tenant_id, :workspace_id, :session_id, :user_input, "
                " :status, now() - interval '2 hour', "
                " now() - interval '2 hour' + interval '5 second', :cost_usd)"
            ),
            [
                {
                    "id": t1,
                    "tenant_id": tenant,
                    "workspace_id": workspace,
                    "session_id": s1,
                    "user_input": "你好",
                    "status": "succeeded",
                    "cost_usd": 0.01,
                },
                {
                    "id": t2,
                    "tenant_id": tenant,
                    "workspace_id": workspace,
                    "session_id": s1,
                    "user_input": "再来",
                    "status": "failed",
                    "cost_usd": 0.02,
                },
                {
                    "id": t3,
                    "tenant_id": tenant,
                    "workspace_id": workspace,
                    "session_id": s2,
                    "user_input": "新会话",
                    "status": "running",
                    "cost_usd": None,
                },
            ],
        )
        await conn.execute(
            text(
                "INSERT INTO agent_session_messages (id, tenant_id, workspace_id, "
                " session_id, turn_id, seq, role, content, tool_name, extra) "
                "VALUES (:id, :tenant_id, :workspace_id, :session_id, :turn_id, "
                " :seq, :role, :content, :tool_name, CAST(:extra AS jsonb))"
            ),
            [
                {
                    "id": uuid4(),
                    "tenant_id": tenant,
                    "workspace_id": workspace,
                    "session_id": s1,
                    "turn_id": t1,
                    "seq": 1,
                    "role": "user",
                    "content": "你好",
                    "tool_name": "",
                    "extra": "{}",
                },
                {
                    "id": uuid4(),
                    "tenant_id": tenant,
                    "workspace_id": workspace,
                    "session_id": s1,
                    "turn_id": t1,
                    "seq": 2,
                    "role": "assistant",
                    "content": "你好，我是助手",
                    "tool_name": "",
                    "extra": "{}",
                },
                {
                    "id": uuid4(),
                    "tenant_id": tenant,
                    "workspace_id": workspace,
                    "session_id": s1,
                    "turn_id": t2,
                    "seq": 1,
                    "role": "user",
                    "content": "再来",
                    "tool_name": "",
                    "extra": "{}",
                },
                {
                    "id": uuid4(),
                    "tenant_id": tenant,
                    "workspace_id": workspace,
                    "session_id": s2,
                    "turn_id": None,  # ⚠️ 挂不上轮次 → 搬不动 ✓
                    "seq": 1,
                    "role": "user",
                    "content": "没有轮次的消息",
                    "tool_name": "",
                    "extra": "{}",
                },
            ],
        )
    return {"tenant": tenant, "s1": s1, "s2": s2, "t1": t1, "t2": t2, "t3": t3}


async def _run_migration(engine, *, direction: str) -> None:
    module = _load_migration()

    def _apply(conn):
        with Operations.context(MigrationContext.configure(conn)):
            if direction == "up":
                module.upgrade()
            else:
                module.downgrade()

    async with engine.begin() as conn:
        await conn.run_sync(_apply)


@pytest.mark.asyncio
async def test_the_legacy_rows_land_in_the_new_tables(db_ctx) -> None:
    engine, _ = db_ctx
    ids = await _prepare(engine)
    await _run_migration(engine, direction="up")

    async with engine.connect() as conn:
        turns = (
            await conn.execute(
                text(
                    "SELECT id::text, status, idempotency_key, model_version "
                    "FROM session_turns ORDER BY created_at"
                )
            )
        ).all()
        messages = (
            await conn.execute(
                text(
                    "SELECT session_id::text, seq, role, content, session_seq "
                    "FROM session_messages ORDER BY session_id, session_seq"
                )
            )
        ).all()
        counters = (
            await conn.execute(
                text("SELECT id::text, next_message_seq FROM agent_sessions ORDER BY id")
            )
        ).all()

    # 历史轮次补齐 ✓（键带 legacy: 前缀 ✓；状态映射 ✓）
    assert len(turns) == 3
    assert {t[1] for t in turns} == {"succeeded", "failed", "running"}
    assert all(t[3] == "legacy" for t in turns)
    assert sum(1 for t in turns if t[2].startswith("legacy:")) == 3

    # 历史消息补齐 ✓ —— 挂不上轮次的那条**搬不动** ✓（不在新表里 ✓）
    assert len(messages) == 3
    assert [m[0] for m in messages].count(str(ids["s1"])) == 3
    assert all(m[4] >= 1 for m in messages)
    # 会话内序号**连续** ✓
    s1_seqs = [m[4] for m in messages if m[0] == str(ids["s1"])]
    assert s1_seqs == [1, 2, 3]

    # 计数器跟着走 ✓
    counters_by_id = {c[0]: c[1] for c in counters}
    assert counters_by_id[str(ids["s1"])] == 3
    assert counters_by_id[str(ids["s2"])] == 0


@pytest.mark.asyncio
async def test_the_dual_written_rows_keep_their_turn(db_ctx) -> None:
    """双写期写进新表的轮次**不被覆盖** ✓（回填只补缺失的 ✓）。"""
    engine, _ = db_ctx
    ids = await _prepare(engine)
    async with engine.begin() as conn:
        await conn.execute(
            SessionTurnORM.__table__.insert(),
            [
                {
                    "id": ids["t3"],
                    "tenant_id": ids["tenant"],
                    "workspace_id": ids["s1"],
                    "session_id": ids["s2"],
                    "idempotency_key": "idem-3",
                    "key_strength": "strong",
                    "status": "running",
                    "agent_version": "v1",
                    "model_version": "m",
                }
            ],
        )
    await _run_migration(engine, direction="up")

    async with engine.connect() as conn:
        row = (
            await conn.execute(
                text("SELECT idempotency_key, model_version FROM session_turns WHERE id = :t"),
                {"t": ids["t3"]},
            )
        ).one()
    assert row[0] == "idem-3"  # ⚠️ 不是 legacy: ✓ —— 原样保留 ✓
    assert row[1] == "m"


@pytest.mark.asyncio
async def test_the_downgrade_removes_the_backfilled_rows(db_ctx) -> None:
    engine, _ = db_ctx
    await _prepare(engine)
    await _run_migration(engine, direction="up")
    await _run_migration(engine, direction="down")

    async with engine.connect() as conn:
        turns = (await conn.execute(text("SELECT count(*) FROM session_turns"))).one()
        messages = (await conn.execute(text("SELECT count(*) FROM session_messages"))).one()
        legacy = (await conn.execute(text("SELECT count(*) FROM agent_session_messages"))).one()
    assert turns[0] == 0
    assert messages[0] == 0
    # 旧表**一行没动** ✓
    assert legacy[0] == 4


__all__ = []
