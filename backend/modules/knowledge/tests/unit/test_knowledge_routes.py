"""**知识域新增的两个端点必须真的落库** ✓。

⚠️ **这两个端点以前根本不存在** ✓ —— 前端「知识源详情 → 同步」与「用户侧知识 →
收藏」在开发模式下**打的是 404** ✓（前端只把收藏记在本地 state 里 ✗）。

验收 ✓：
- 收藏 → ``admin_knowledge_doc_user_state`` **真有一行** ✓，且**按用户隔离** ✓；
- 同步 → 数据源行**真的被更新** ✓（条目数 / 状态 ✓）。
"""

from __future__ import annotations

import os
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from qzdap.modules.knowledge.adapter.http.router import build_router
from qzdap.modules.knowledge.adapter.persistence.models import (
    KnowledgeBaseORM,
    KnowledgeChunkORM,
    KnowledgeDocORM,
    KnowledgeDocUserStateORM,
    KnowledgeSourceORM,
)
from qzdap.modules.knowledge.adapter.persistence.repositories import (
    SqlKnowledgeCatalogRepository,
    SqlKnowledgeDocUserStateRepository,
)
from qzdap.modules.knowledge.application.services import KnowledgeService
from qzdap_persistence.session_factory import SessionFactory

_TENANT = uuid4()
_WORKSPACE = uuid4()
_USER = uuid4()


@pytest.fixture
async def client():
    dsn = os.environ.get("QZDAP_TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("set QZDAP_TEST_DATABASE_URL to run PostgreSQL HTTP roundtrips")
    schema = f"knowledge_test_{uuid4().hex}"
    engine = create_async_engine(dsn, connect_args={"server_settings": {"search_path": schema}})
    async with engine.begin() as conn:
        await conn.execute(text(f"CREATE SCHEMA {schema}"))
        for table in (
            KnowledgeBaseORM.__table__,
            KnowledgeDocORM.__table__,
            KnowledgeChunkORM.__table__,
            KnowledgeSourceORM.__table__,
            KnowledgeDocUserStateORM.__table__,
        ):
            await conn.run_sync(table.create)
    sf = SessionFactory(engine)

    class _Factory:
        def for_session(self, session):  # type: ignore[no-untyped-def]
            return KnowledgeService(
                SqlKnowledgeCatalogRepository(session),
                user_state=SqlKnowledgeDocUserStateRepository(session),
            )

    app = FastAPI()
    app.include_router(build_router())
    app.state.knowledge_service_factory = _Factory()
    app.state.container = type("_Container", (), {"session_factory": staticmethod(lambda: sf)})()
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
        headers={
            "X-Tenant-Id": str(_TENANT),
            "X-Workspace-Id": str(_WORKSPACE),
            "X-User-Id": str(_USER),
        },
    ) as http:
        yield http, sf
    async with engine.begin() as conn:
        await conn.execute(text(f"DROP SCHEMA {schema} CASCADE"))
    await engine.dispose()


async def _rows(sf: SessionFactory, sql: str) -> list[tuple[object, ...]]:
    async with sf.session() as session:
        result = await session.execute(text(sql))
        return [tuple(row) for row in result.all()]


async def _seed(client: AsyncClient) -> tuple[str, str]:
    """建一个知识库 + 一个数据源 + 一篇挂在该数据源下的文档 ✓."""
    kb = await client.post(
        "/api/admin/knowledge/kbs",
        json={"name": "制度库", "description": "制度文档", "scope": "公开"},
    )
    assert kb.status_code == 201, kb.text
    source = await client.post(
        "/api/admin/knowledge/sources",
        json={"name": "Notion 空间", "type": "notion"},
    )
    assert source.status_code == 201, source.text
    doc = await client.post(
        "/api/admin/knowledge/docs",
        json={
            "kbId": kb.json()["id"],
            "name": "报销制度.md",
            "content": "差旅报销的标准与时限",
            "sourceId": source.json()["id"],
        },
    )
    assert doc.status_code == 201, doc.text
    return source.json()["id"], doc.json()["id"]


async def test_favorite_writes_a_row_and_is_per_user(client) -> None:
    """**收藏要落库** ✓（以前只在浏览器内存里 ✗）。"""
    http, sf = client
    _source_id, doc_id = await _seed(http)

    resp = await http.post(f"/api/catalog/knowledge/{doc_id}/favorite", json={"on": True})
    assert resp.status_code == 200, resp.text
    assert resp.json()["favorited"] is True

    rows = await _rows(sf, "select user_id, doc_id, favorited from admin_knowledge_doc_user_state")
    assert [(str(r[0]), str(r[1]), r[2]) for r in rows] == [(str(_USER), doc_id, True)]

    listed = await http.get("/api/catalog/knowledge", params={"only_favorites": "true"})
    assert listed.status_code == 200, listed.text
    assert [row["id"] for row in listed.json()] == [doc_id]


async def test_sync_source_updates_the_source_row(client) -> None:
    """**同步要把数据源真的更新掉** ✓（条目数 / 状态 ✓）。"""
    http, sf = client
    source_id, _doc_id = await _seed(http)

    resp = await http.post(f"/api/admin/knowledge/sources/{source_id}/sync")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["synced"] == 1
    assert body["failed"] == 0
    assert body["mode"] == "reindex"
    assert body["itemCount"] == 1

    rows = await _rows(sf, "select item_count, status from admin_knowledge_sources")
    assert [(r[0], r[1]) for r in rows] == [(1, "online")]


async def test_sync_unknown_source_is_404(client) -> None:
    http, _sf = client
    resp = await http.post(f"/api/admin/knowledge/sources/{uuid4()}/sync")
    assert resp.status_code == 404, resp.text
