"""Gateway ④ 幂等守卫 —— 真库 + 真并发。

覆盖 Gateway 方案 §10 Stage 1 的验收：
同键并发只起 1 轮 · weak 不误杀 · 过期不误杀 · 审批不重复执行 · 跨进程可见。
"""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import UTC, datetime

import pytest
from qzdap_agent_runtime.gateway.idempotency import (
    IdempotencyGuard,
    InboxScope,
    approval_key,
    client_request_key,
    payload_fingerprint_key,
)
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from qzdap.modules.agent_runtime.adapter.persistence.idempotency_store import (
    PostgresIdempotencyStore,
)

_DDL = [
    """
CREATE TABLE "{schema}".session_inbox (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    channel_id varchar(128) NOT NULL,
    external_message_id varchar(256),
    payload_hash varchar(64) NOT NULL,
    turn_id uuid,
    trace_id varchar(64),
    received_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    idempotency_key varchar(128) NOT NULL,
    key_source varchar(32) NOT NULL,
    key_strength varchar(8) NOT NULL,
    status varchar(16) NOT NULL DEFAULT 'received',
    claimed_at timestamptz,
    expires_at timestamptz NOT NULL
)
""",
    """
CREATE UNIQUE INDEX uq_session_inbox_idem_strong
    ON "{schema}".session_inbox (tenant_id, workspace_id, channel_id, idempotency_key)
    WHERE key_strength = 'strong'
""",
    """
CREATE INDEX ix_session_inbox_expires ON "{schema}".session_inbox (expires_at)
""",
]


@pytest.fixture
async def inbox_db():
    url = os.environ.get("QZDAP_TEST_DATABASE_URL")
    if not url:
        pytest.skip("QZDAP_TEST_DATABASE_URL is not set")
    schema = "idempotency_" + uuid.uuid4().hex
    admin = create_async_engine(url)
    async with admin.connect() as conn:
        await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        for statement in _DDL:
            await conn.execute(text(statement.format(schema=schema)))
        await conn.commit()

    # 每条连接都要在自己的 schema 里 —— search_path 走连接参数.
    engine = create_async_engine(
        url, connect_args={"server_settings": {"search_path": schema}}
    )
    from qzdap_persistence.session_factory import SessionFactory

    store = PostgresIdempotencyStore(SessionFactory(engine))
    try:
        yield store, engine
    finally:
        await engine.dispose()
        async with admin.connect() as conn:
            await conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
            await conn.commit()
        await admin.dispose()


def _scope() -> InboxScope:
    return InboxScope.for_web(tenant_id=uuid.uuid4(), workspace_id=uuid.uuid4())


async def test_the_same_strong_key_concurrently_starts_only_one_turn(inbox_db) -> None:
    store, _engine = inbox_db
    scope = _scope()
    key = client_request_key("req-concurrent")

    decisions = await asyncio.gather(
        *(store.claim(scope, key, payload_hash="h") for _ in range(10))
    )

    outcomes = [d.outcome for d in decisions]
    assert outcomes.count("new") == 1, outcomes
    assert all(o in {"duplicate", "in_progress"} for o in outcomes if o != "new")
    assert len({d.row_id for d in decisions}) == 1


async def test_a_completed_key_blocks_a_second_turn(inbox_db) -> None:
    store, _engine = inbox_db
    scope = _scope()
    key = client_request_key("req-done")

    first = await store.claim(scope, key, payload_hash="h")
    assert first.outcome == "new"
    await store.mark_completed(first.row_id, turn_id=uuid.uuid4())

    second = await store.claim(scope, key, payload_hash="h")
    assert second.outcome == "duplicate"
    assert second.row_id == first.row_id


async def test_a_different_key_is_not_treated_as_a_duplicate(inbox_db) -> None:
    """不同幂等键不是重复请求 —— 各自都要放行。"""
    store, _engine = inbox_db
    scope = _scope()

    first = await store.claim(scope, client_request_key("req-a"), payload_hash="h")
    second = await store.claim(scope, client_request_key("req-b"), payload_hash="h")

    assert first.outcome == "new"
    assert second.outcome == "new"
    assert first.row_id != second.row_id


async def test_a_weak_key_never_suppresses(inbox_db) -> None:
    """决策 #5 —— 用户连发两条「好的」必须两轮都跑。"""
    store, engine = inbox_db
    scope = _scope()
    now = datetime.now(UTC)
    key = payload_fingerprint_key(
        channel="web", chat_id="s1", user_id="u1", text="好的", now=now
    )

    first = await store.record_weak(scope, key, payload_hash="h")
    second = await store.record_weak(scope, key, payload_hash="h")

    assert first.outcome == "new"
    assert second.outcome == "new"
    assert first.row_id != second.row_id
    async with engine.connect() as conn:
        count = (
            await conn.execute(
                text("select count(*) from session_inbox where key_strength = 'weak'")
            )
        ).scalar()
    assert count == 2


async def test_an_expired_key_is_treated_as_a_new_message(inbox_db) -> None:
    """同一个 clientRequestId 在 TTL 之后重发 —— 不得判重复。"""
    store, engine = inbox_db
    scope = _scope()
    key = client_request_key("req-expired")

    await store.claim(scope, key, payload_hash="h")
    async with engine.begin() as conn:
        await conn.execute(
            text("update session_inbox set expires_at = now() - interval '1 hour'")
        )

    decision = await store.claim(scope, key, payload_hash="h")
    assert decision.outcome == "taken_over"
    assert decision.should_run

    async with engine.connect() as conn:
        count = (
            await conn.execute(text("select count(*) from session_inbox"))
        ).scalar()
    assert count == 1


async def test_the_approval_key_dedupes_a_double_click(inbox_db) -> None:
    """连点两次「同意」—— 第二次必须被判定为重复。"""
    store, _engine = inbox_db
    scope = _scope()
    approval = uuid.uuid4()

    first = await store.claim(
        scope, approval_key(str(approval), "approved"), payload_hash="h"
    )
    assert first.outcome == "new"

    second = await store.claim(
        scope, approval_key(str(approval), "approved"), payload_hash="h"
    )
    assert second.outcome == "in_progress"
    assert second.is_duplicate

    # 拒绝是另一次决策 —— 不该被上面那次「同意」误伤.
    deny = await store.claim(
        scope, approval_key(str(approval), "denied"), payload_hash="h"
    )
    assert deny.outcome == "new"


async def test_release_frees_the_key_for_a_retry(inbox_db) -> None:
    """会话被占着而没跑起来 —— 键不能被消费，否则重试会被误判重复。"""
    store, engine = inbox_db
    scope = _scope()
    key = client_request_key("req-busy")

    first = await store.claim(scope, key, payload_hash="h")
    assert first.outcome == "new"
    await store.release(first.row_id)

    second = await store.claim(scope, key, payload_hash="h")
    assert second.outcome == "new"
    async with engine.connect() as conn:
        count = (
            await conn.execute(text("select count(*) from session_inbox"))
        ).scalar()
    assert count == 1


async def test_the_sweeper_removes_expired_rows(inbox_db) -> None:
    store, engine = inbox_db
    scope = _scope()
    await store.claim(scope, client_request_key("req-old"), payload_hash="h")
    async with engine.begin() as conn:
        await conn.execute(
            text("update session_inbox set expires_at = now() - interval '1 hour'")
        )

    removed = await store.sweep_expired()
    assert removed == 1
    async with engine.connect() as conn:
        count = (
            await conn.execute(text("select count(*) from session_inbox"))
        ).scalar()
    assert count == 0


async def test_the_guard_marks_the_row_completed(inbox_db) -> None:
    store, engine = inbox_db
    guard = IdempotencyGuard(store)
    scope = _scope()

    decision = await guard.accept(
        scope, client_request_key("req-guard"), payload_hash="h"
    )
    assert decision.should_run
    await guard.complete(decision, turn_id=uuid.uuid4())

    async with engine.connect() as conn:
        row = (
            await conn.execute(
                text("select status, turn_id from session_inbox limit 1")
            )
        ).first()
    assert row[0] == "completed"
    assert row[1] is not None
