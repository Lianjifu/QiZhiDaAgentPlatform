"""**agent_factory 的写必须落库** ✓（与 platform 同一个病 ✓ → 一起修 ✓）。

⚠️ **以前这个域的写全部丢** ✓ —— 请求依赖**只开会话** ✓，**既不提交也不回滚**
✓ → 请求一结束事务就回滚 ✓ → 建模板返回 201 ✓ 但**库里没有那一行** ✓。

验收 ✓：**响应 201 且再读得到** ✓。
"""

from __future__ import annotations

import os
from typing import Any, cast
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from qzdap.modules.agent_factory.adapter.http.router import build_router
from qzdap.modules.agent_factory.adapter.persistence.models import (
    AgentTemplateORM,
    AgentVersionORM,
    ReleaseORM,
)
from qzdap.modules.agent_factory.application.services import AgentFactoryService
from qzdap_persistence.session_factory import SessionFactory

_TENANT = uuid4()
_WORKSPACE = uuid4()
_MODEL = uuid4()


@pytest.fixture
async def client():
    dsn = os.environ.get("QZDAP_TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("set QZDAP_TEST_DATABASE_URL to run PostgreSQL HTTP roundtrips")
    schema = f"agent_factory_test_{uuid4().hex}"
    engine = create_async_engine(dsn, connect_args={"server_settings": {"search_path": schema}})
    async with engine.begin() as conn:
        await conn.execute(text(f"CREATE SCHEMA {schema}"))
        await conn.run_sync(AgentTemplateORM.__table__.create)
        await conn.run_sync(AgentVersionORM.__table__.create)
        await conn.run_sync(ReleaseORM.__table__.create)
    sf = SessionFactory(engine)
    app = FastAPI()
    app.include_router(build_router())

    class _Factory:
        def for_session(self, session):  # type: ignore[no-untyped-def]
            from qzdap.modules.agent_factory.adapter.persistence.repositories import (
                SqlAgentTemplateRepository,
                SqlAgentVersionRepository,
                SqlReleaseRepository,
            )

            return AgentFactoryService.from_parts(
                template_repository=SqlAgentTemplateRepository(session),
                version_repository=SqlAgentVersionRepository(session),
                release_repository=SqlReleaseRepository(session),
                evaluation_query=cast("Any", None),
            )

    app.state.agent_factory_service_factory = _Factory()
    app.state.container = type("_Container", (), {"session_factory": staticmethod(lambda: sf)})()
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
        headers={
            "X-Tenant-Id": str(_TENANT),
            "X-Workspace-Id": str(_WORKSPACE),
            "X-User-Id": str(uuid4()),
        },
    ) as http:
        yield http
    async with engine.begin() as conn:
        await conn.execute(text(f"DROP SCHEMA {schema} CASCADE"))
    await engine.dispose()


async def test_creating_a_template_actually_persists(client):
    """**写进去就要读得到** ✓（以前返回 201 但库里是空的 ✓）。"""
    created = await client.post(
        "/v1/agents",
        json={
            "name": "临时模板",
            "description": "类型检查用",
            "default_model_id": str(_MODEL),
            "default_system_prompt": "你是助手",
        },
    )
    assert created.status_code == 201, created.text
    aid = created.json()["id"]

    fetched = await client.get(f"/v1/agents/{aid}")
    assert fetched.status_code == 200, fetched.text
    assert fetched.json()["name"] == "临时模板"
