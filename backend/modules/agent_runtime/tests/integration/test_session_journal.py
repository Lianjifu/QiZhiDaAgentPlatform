"""新架构的轮次 + 事件日志 —— **真库**（``session_turns`` / ``session_events``）。

覆盖 Gateway Stage 4b 的落地前提（§4.5：``session_events`` **真写真读**）：

- 轮次写进去了、事件按 seq 递增写进去了；
- 按 ``after_seq`` 读得到「续传的那一段」；
- **跨租户读不到**（事件表没有 ``tenant_id`` 列，租户靠 JOIN 轮次表保证）；
- **weak 键不互相冲突**（决策 #5）——两条内容相同的消息都能落轮次；
- **strong 键不重复起轮次** ——在飞的同键轮次撞唯一索引；
- 轮次落终态后，同一把键**还能再用**（TTL 到期重发不被这层约束反噬）。
"""

from __future__ import annotations

import os
import uuid
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from qzdap.modules.agent_runtime.adapter.persistence.session_journal import (
    PostgresSessionJournal,
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
    -- ⚠️ **Router 的入站序号** ✓（迁移 0045 ✓ —— 排队语义用 ✓）。
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
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    pending_approval jsonb,
    cancel_requested boolean NOT NULL DEFAULT false,
    ingress_seq integer,
    route_decision jsonb,
    agent_decision jsonb,
    CONSTRAINT session_turns_status_enum CHECK (
        status IN ('queued','running','waiting','succeeded','failed','cancelled')
    )
)
""",
    """
CREATE UNIQUE INDEX uq_session_turns_session_idem_strong
    ON "{schema}".session_turns (session_id, idempotency_key)
    WHERE key_strength = 'strong'
      AND status IN ('queued','running','waiting')
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
    PRIMARY KEY (turn_id, seq),
    CONSTRAINT session_events_status_enum CHECK (
        delivery_status IN ('pending','delivered','failed','dead_letter')
    )
)
""",
]


@pytest.fixture
async def journal_ctx():
    url = os.environ.get("QZDAP_TEST_DATABASE_URL")
    if not url:
        pytest.skip("QZDAP_TEST_DATABASE_URL is not set")
    schema = "journal_" + uuid.uuid4().hex
    admin = create_async_engine(url)
    async with admin.connect() as conn:
        await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        for statement in _DDL:
            await conn.execute(text(statement.replace("{schema}", schema)))
        await conn.commit()

    engine = create_async_engine(url, connect_args={"server_settings": {"search_path": schema}})
    from qzdap_persistence.session_factory import SessionFactory

    factory = SessionFactory(engine)
    store = PostgresSessionJournal(factory)
    try:
        yield store, factory
    finally:
        await engine.dispose()
        async with admin.connect() as conn:
            await conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            await conn.commit()
        await admin.dispose()


async def _session(factory, *, tenant_id: UUID) -> UUID:  # type: ignore[no-untyped-def]
    """建一个会话行（轮次的外键父行）。"""
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


async def _start(
    store: PostgresSessionJournal,
    *,
    session_id: UUID,
    tenant_id: UUID,
    key: str,
    strength: str = "strong",
    turn_id: UUID | None = None,
) -> UUID:
    turn_id = turn_id or uuid4()
    await store.start_turn(
        turn_id=turn_id,
        tenant_id=tenant_id,
        workspace_id=uuid4(),
        session_id=session_id,
        idempotency_key=key,
        key_strength=strength,
        agent_version="v1",
        model_version="default",
    )
    return turn_id


@pytest.mark.asyncio
async def test_a_turn_and_its_events_round_trip(journal_ctx) -> None:  # type: ignore[no-untyped-def]
    journal, factory = journal_ctx
    tenant = uuid4()
    session_id = await _session(factory, tenant_id=tenant)
    turn_id = await _start(journal, session_id=session_id, tenant_id=tenant, key="k1")

    for seq in (1, 2, 3):
        await journal.append_event(
            turn_id=turn_id,
            seq=seq,
            event_type="message",
            payload={"seq": seq, "kind": "message", "content": f"c{seq}"},
        )

    events = await journal.get_events(turn_id, tenant_id=tenant)
    assert [event.seq for event in events] == [1, 2, 3]
    assert events[0].payload["content"] == "c1"
    assert await journal.get_turn_status(turn_id, tenant_id=tenant) == "running"

    await journal.finish_turn(turn_id=turn_id, status="succeeded")
    assert await journal.get_turn_status(turn_id, tenant_id=tenant) == "succeeded"


@pytest.mark.asyncio
async def test_reading_after_a_seq_returns_only_the_tail(journal_ctx) -> None:  # type: ignore[no-untyped-def]
    """断线续传：``after_seq`` 之后的那几段。"""
    journal, factory = journal_ctx
    tenant = uuid4()
    session_id = await _session(factory, tenant_id=tenant)
    turn_id = await _start(journal, session_id=session_id, tenant_id=tenant, key="k1")
    for seq in (1, 2, 3):
        await journal.append_event(
            turn_id=turn_id, seq=seq, event_type="message", payload={"seq": seq}
        )

    tail = await journal.get_events(turn_id, tenant_id=tenant, after_seq=2)
    assert [event.seq for event in tail] == [3]
    assert await journal.get_events(turn_id, tenant_id=tenant, after_seq=3) == []


@pytest.mark.asyncio
async def test_another_tenant_sees_nothing(journal_ctx) -> None:  # type: ignore[no-untyped-def]
    """⚠️ 事件表**没有** ``tenant_id`` 列 —— 租户隔离靠 JOIN 轮次表。"""
    journal, factory = journal_ctx
    tenant = uuid4()
    other = uuid4()
    session_id = await _session(factory, tenant_id=tenant)
    turn_id = await _start(journal, session_id=session_id, tenant_id=tenant, key="k1")
    await journal.append_event(turn_id=turn_id, seq=1, event_type="message", payload={"seq": 1})

    assert await journal.get_events(turn_id, tenant_id=other) == []
    assert await journal.get_turn_status(turn_id, tenant_id=other) is None


@pytest.mark.asyncio
async def test_two_weak_keys_with_the_same_value_both_land(journal_ctx) -> None:  # type: ignore[no-untyped-def]
    """**weak 键不互相抑制**（决策 #5）—— 唯一索引不覆盖 weak 行。"""
    journal, factory = journal_ctx
    tenant = uuid4()
    session_id = await _session(factory, tenant_id=tenant)
    first = await _start(
        journal, session_id=session_id, tenant_id=tenant, key="same", strength="weak"
    )
    second = await _start(
        journal, session_id=session_id, tenant_id=tenant, key="same", strength="weak"
    )
    assert first != second
    assert await journal.get_turn_status(first, tenant_id=tenant) == "running"
    assert await journal.get_turn_status(second, tenant_id=tenant) == "running"


@pytest.mark.asyncio
async def test_a_second_in_flight_strong_key_is_rejected(journal_ctx) -> None:  # type: ignore[no-untyped-def]
    """**同一会话里不得有两个在飞的同键轮次**（兜底约束）。"""
    journal, factory = journal_ctx
    tenant = uuid4()
    session_id = await _session(factory, tenant_id=tenant)
    await _start(journal, session_id=session_id, tenant_id=tenant, key="same")

    with pytest.raises(IntegrityError):
        await _start(journal, session_id=session_id, tenant_id=tenant, key="same")


@pytest.mark.asyncio
async def test_a_finished_strong_key_can_be_used_again(journal_ctx) -> None:  # type: ignore[no-untyped-def]
    """轮次落终态后同键可再用 —— **TTL 到期重发不被这层约束反噬**。"""
    journal, factory = journal_ctx
    tenant = uuid4()
    session_id = await _session(factory, tenant_id=tenant)
    first = await _start(journal, session_id=session_id, tenant_id=tenant, key="same")
    await journal.finish_turn(turn_id=first, status="succeeded")

    second = await _start(journal, session_id=session_id, tenant_id=tenant, key="same")
    assert second != first
    assert await journal.get_turn_status(second, tenant_id=tenant) == "running"


@pytest.mark.asyncio
async def test_a_turn_written_by_the_copilot_replays_with_the_same_digest(
    journal_ctx,
) -> None:  # type: ignore[no-untyped-def]
    """**验收**：copilot 跑一轮 → 事件真落库 → 门面重放 → 摘要与原流一致。

    这是 Gateway Stage 4b 的核心验收（§10）：「重放拼接结果与原流 chunk 序列的
    hash 相同、seq 连续」。
    """
    from _ar_unit_in_memory import (
        FakeLLM,
        InMemoryIdempotencyStore,
        InMemorySessionRepository,
        InMemoryTurnClaim,
        InMemoryTurnRepository,
        RecordingEventPublisher,
        make_turn_runner,
    )

    from qzdap.modules.agent_runtime.adapter.graph.runner import SessionGraphRunner
    from qzdap.modules.agent_runtime.application.copilot import CopilotSessionService
    from qzdap.modules.agent_runtime.domain.catalog import CatalogAgent
    from qzdap_agent_runtime.gateway.facade import Gateway
    from qzdap_agent_runtime.gateway.idempotency import IdempotencyGuard
    from qzdap_agent_runtime.gateway.replay import event_digest, event_from_chunk
    from qzdap_agent_runtime.gateway.types import ChannelType
    from qzdap_agent_runtime.gateway.web import WebChatNormalizer, WebIdentityVerifier
    from qzdap_schema.ids import AgentId, TenantId, UserId, WorkspaceId

    journal, factory = journal_ctx
    tenant = uuid4()
    owner = UserId(uuid4())

    class _Catalog:
        def __init__(self, agent: CatalogAgent) -> None:
            self._agent = agent

        async def get_published(self, agent_id):  # type: ignore[no-untyped-def]
            return self._agent

    class _Messages:
        async def list_for_session(self, session_id):  # type: ignore[no-untyped-def]
            return []

        async def append(self, **kwargs):  # type: ignore[no-untyped-def]
            return None

        async def next_seq(self, *, session_id):  # type: ignore[no-untyped-def]
            return 0

    agent = CatalogAgent.create(
        id=AgentId(uuid4()),
        tenant_id=TenantId(tenant),
        workspace_id=WorkspaceId(uuid4()),
        name="t",
        category="test",
        owner="test",
        model="default",
    )
    sessions = InMemorySessionRepository()
    messages = _Messages()  # type: ignore[arg-type]
    runner = SessionGraphRunner(llm=FakeLLM(content="hi back"))
    events = RecordingEventPublisher()
    svc = CopilotSessionService(
        sessions=sessions,
        turns=InMemoryTurnRepository(journal),
        messages=messages,  # type: ignore[arg-type]
        catalog=_Catalog(agent),  # type: ignore[arg-type]
        events=events,
        graph=runner,
        idempotency=IdempotencyGuard(InMemoryIdempotencyStore()),
        journal=journal,
        claim=InMemoryTurnClaim(),
        turn_runner=make_turn_runner(
            graph=runner,
            journal=journal,
            events=events,
            messages=messages,
            sessions=sessions,
        ),
    )
    detail = await svc.create_session(
        tenant_id=TenantId(tenant),
        workspace_id=agent.workspace_id,
        owner_id=owner,
        agent_id=agent.id,
    )
    session_id = UUID(detail["id"])
    # 轮次的外键父行必须真的在库里 —— 会话行是**旧表**的，这里补一条。
    async with factory.session() as db, db.begin():
        await db.execute(
            text(
                "INSERT INTO agent_sessions "
                "(id, tenant_id, workspace_id, owner_id, agent_id, agent_version) "
                "VALUES (:id, :tenant, :ws, :owner, :agent, 'v1')"
            ),
            {
                "id": session_id,
                "tenant": tenant,
                "ws": agent.workspace_id,
                "owner": owner,
                "agent": agent.id,
            },
        )

    chunks = [
        chunk
        async for chunk in svc.stream_turn(
            tenant_id=TenantId(tenant),
            workspace_id=agent.workspace_id,
            owner_id=owner,
            session_id=session_id,
            user_input="hi",
            client_request_id="req-1",
        )
    ]
    assert chunks, "这一轮应当产出 chunk"

    # 原流的事件序列（与落库用的是同一份载荷）。
    original = [event_from_chunk(chunk) for chunk in chunks]
    turn_id = chunks[0].turn_id

    # 门面重放 —— 与生产装配同型。
    gateway = Gateway(
        channels=None,
        identity=WebIdentityVerifier(),
        normalizers={ChannelType.WEB: WebChatNormalizer()},
        idempotency=IdempotencyGuard(InMemoryIdempotencyStore()),
        events=journal,
    )
    result = await gateway.replay(turn_id, tenant_id=tenant)

    assert event_digest(result.events) == event_digest(original)
    # seq 连续。
    assert [event.seq for event in result.events] == list(range(1, len(result.events) + 1))
    assert result.is_finished is True


@pytest.mark.asyncio
async def test_a_zombie_turn_does_not_block_the_key_forever(journal_ctx) -> None:  # type: ignore[no-untyped-def]
    """**僵尸接管**：进程死了留下的在飞行（很久以前）→ 接管，不再挡着这把键。

    年轻的撞键行**照旧报错**（那是真的重复执行，必须被挡住）—— 见
    `test_a_second_in_flight_strong_key_is_rejected`。
    """
    journal, factory = journal_ctx
    tenant = uuid4()
    session_id = await _session(factory, tenant_id=tenant)
    zombie = await _start(journal, session_id=session_id, tenant_id=tenant, key="same")
    # 把第一行改成「很久以前就起飞了、然后进程死了」。
    async with factory.session() as db, db.begin():
        await db.execute(
            text("UPDATE session_turns SET started_at = now() - interval '2 hours' WHERE id = :id"),
            {"id": zombie},
        )

    second = await _start(journal, session_id=session_id, tenant_id=tenant, key="same")
    assert second != zombie
    assert await journal.get_turn_status(zombie, tenant_id=tenant) == "failed"
    assert await journal.get_turn_status(second, tenant_id=tenant) == "running"
