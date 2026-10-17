"""Phase 19: agent_factory.version.released → agent_runtime.CatalogAgent 集成测试.

测试 subscriber 实际通过 in-process bus 接收 envelope, 改 catalog 行的
status / version / audit_events. 用真实的 PostgreSQL (per-test schema 隔离).
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from qzdap.modules.agent_runtime.adapter.persistence.catalog_models import (
    CatalogAgentORM,
)
from qzdap.modules.agent_runtime.adapter.persistence.catalog_repositories import (
    SqlCatalogAgentRepository,
)
from qzdap.modules.agent_runtime.adapter.subscribers import (
    agent_factory_release_subscriber as sub,
)
from qzdap.modules.agent_runtime.domain.catalog import CatalogAgent


@pytest.fixture
async def catalog_db_session():
    """Per-test schema with admin_agents 表."""
    url = os.environ.get("QZDAP_TEST_DATABASE_URL")
    if not url:
        pytest.skip("QZDAP_TEST_DATABASE_URL is not set")
    engine = create_async_engine(url)
    schema = "agent_factory_rel_" + uuid4().hex
    async with engine.connect() as connection:
        transaction = await connection.begin()
        await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        await connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
        await connection.run_sync(
            lambda conn: CatalogAgentORM.__table__.create(conn)
        )

        @asynccontextmanager
        async def session():
            yield AsyncSession(
                bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
            )

        try:
            yield session
        finally:
            await transaction.rollback()
    await engine.dispose()


def _envelope_obj(
    template_id: UUID,
    *,
    version_tag: str = "v1",
    eval_score: float | None = 0.85,
):
    """构造一个 EventEnvelope-like 对象 (bus.publish 严格用 attr).

    InProcessBus.publish 走 envelope.event_name + envelope.payload, 因此用
    SimpleNamespace 包一层即可, 不必 import EventEnvelope.
    """
    from types import SimpleNamespace

    return SimpleNamespace(
        event_name="agent_factory.version.released",
        payload={
            "release_id": str(uuid4()),
            "template_id": str(template_id),
            "version_id": str(uuid4()),
            "tenant_id": str(uuid4()),
            "workspace_id": str(uuid4()),
            "version_tag": version_tag,
            "eval_score": eval_score,
            "released_by": str(uuid4()),
        },
    )


async def _seed_catalog_agent(
    session_factory, *, template_id: UUID | None = None
) -> UUID:
    """直接 INSERT 一条 catalog row, 返回 agent.id."""
    aid = template_id or uuid4()
    async with session_factory() as db:
        agent = CatalogAgent.create(
            id=aid,
            tenant_id=uuid4(),
            workspace_id=uuid4(),
            name="test-agent",
            category="企业通用",
            owner="admin",
        )
        # 让它不是 draft, 模拟"已经 admin 配置过"的状态
        from dataclasses import replace
        from datetime import UTC, datetime

        agent = replace(
            agent, status="draft", version="draft", updated_at=datetime.now(UTC)
        )
        await SqlCatalogAgentRepository(db).add(agent)
        await db.commit()
    return aid


@pytest.mark.asyncio
async def test_release_event_publishes_catalog_agent(catalog_db_session):
    """happy path: catalog 行存在 (id == template_id), 收到事件后 status='published'."""
    session_factory = catalog_db_session
    template_id = uuid4()
    await _seed_catalog_agent(session_factory, template_id=template_id)

    envelope = _envelope_obj(template_id, version_tag="v1", eval_score=0.92)

    async with session_factory() as db:
        handler = sub.build_handler(db)
        await handler(envelope)
        await db.commit()

    # 读回
    async with session_factory() as db:
        row = await SqlCatalogAgentRepository(db).get(template_id)
        assert row is not None, f"catalog row for {template_id} not found"
        assert row.status == "published", f"expected published, got {row.status!r}"
        assert row.version == "v1", f"expected v1, got {row.version!r}"
        # 至少一条 audit 是工厂发布
        factory_events = [e for e in row.audit_events if e.get("action") == "工厂发布"]
        assert len(factory_events) == 1, f"expected 1 工厂发布 audit, got {factory_events}"
        assert "v1" in factory_events[0]["detail"]
        assert "0.92" in factory_events[0]["detail"]


@pytest.mark.asyncio
async def test_release_event_no_matching_catalog_silently_skips(catalog_db_session):
    """无对应 catalog 行 → silent skip, 不抛错."""
    session_factory = catalog_db_session
    template_id = uuid4()  # 不 seed

    envelope = _envelope_obj(template_id, version_tag="v1")

    async with session_factory() as db:
        handler = sub.build_handler(db)
        # 不抛错
        await handler(envelope)
        await db.commit()

    # 任何 catalog 行都没动
    async with session_factory() as db:
        row = await SqlCatalogAgentRepository(db).get(template_id)
        assert row is None


@pytest.mark.asyncio
async def test_release_event_garbage_envelope_returns_silently(catalog_db_session):
    """envelope 缺 template_id / payload 不是 dict → 静默 skip."""
    session_factory = catalog_db_session

    async with session_factory() as db:
        handler = sub.build_handler(db)
        # payload 是 None
        await handler(SimpleNamespace(event_name="agent_factory.version.released", payload=None))
        # event_name 不匹配
        await handler(SimpleNamespace(event_name="something.else", payload={"template_id": str(uuid4())}))
        await db.commit()


@pytest.mark.asyncio
async def test_release_subscriber_installs_on_bus_and_processes(catalog_db_session):
    """端到端: 装在 InProcessBus, publish 后 catalog 状态更新."""
    from qzdap_messaging.in_process import InProcessBus

    session_factory = catalog_db_session
    template_id = uuid4()
    await _seed_catalog_agent(session_factory, template_id=template_id)

    bus = InProcessBus()
    await bus.start()
    try:
        # session_opener 模拟: 直接是 async context manager factory
        await sub.install(bus, session_factory)
        # publish 一个 dict-style envelope
        envelope = _envelope_obj(template_id, version_tag="v2", eval_score=0.78)
        # InProcessBus.publish 接受任意 envelope (鸭子类型)
        await bus.publish(envelope)
        # handler 异步, 给点时间
        import asyncio

        await asyncio.sleep(0.05)
    finally:
        await bus.stop()

    # 读回
    async with session_factory() as db:
        row = await SqlCatalogAgentRepository(db).get(template_id)
        assert row is not None
        assert row.status == "published"
        assert row.version == "v2"
        # versions[0] 应该是新发布的 (current=True, snapshot=agent 当前配置)
        assert len(row.versions) >= 1
        head = row.versions[0]
        assert head["version"] == "v2"
        assert head["current"] is True
        assert "snapshot" in head
