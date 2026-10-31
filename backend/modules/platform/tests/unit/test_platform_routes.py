"""**平台的写必须落库** ✓（P-13 顺带修出来的真缺陷 ✓）。

⚠️ **以前平台域的写全部丢** ✓ —— 请求依赖**只开会话** ✓，**既不提交也不回滚**
✓ → 请求一结束事务就回滚 ✓ → `PUT /v1/platform/subscriptions/me` **返回 200** ✓
但**库里没有那一行** ✓（订阅的写路径还有第二个雷 ✓ —— 领域实体没有
`workspace_id` ✓ 而 ORM 映射了它 ✓ → `AttributeError` ✓ —— 两个都修掉才真的
写得进去 ✓）。

验收 ✓：**响应 200 且库里真有一行** ✓。
"""

from __future__ import annotations

import os
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from qzdap.modules.platform.adapter.http.router import build_router
from qzdap.modules.platform.adapter.persistence.models import (
    PlanORM,
    SubscriptionORM,
    TenantSettingORM,
)
from qzdap.modules.platform.application.services import PlatformService
from qzdap_persistence.session_factory import SessionFactory

_TENANT = uuid4()
_WORKSPACE = uuid4()


@pytest.fixture
async def client():
    dsn = os.environ.get("QZDAP_TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("set QZDAP_TEST_DATABASE_URL to run PostgreSQL HTTP roundtrips")
    schema = f"platform_test_{uuid4().hex}"
    engine = create_async_engine(dsn, connect_args={"server_settings": {"search_path": schema}})
    async with engine.begin() as conn:
        await conn.execute(text(f"CREATE SCHEMA {schema}"))
        await conn.run_sync(PlanORM.__table__.create)
        await conn.run_sync(SubscriptionORM.__table__.create)
        await conn.run_sync(TenantSettingORM.__table__.create)
        await conn.execute(
            text(
                "INSERT INTO plans (id, code, display_name, description, limits, features, "
                "price_monthly_usd, status, sort_order, created_at, updated_at) VALUES "
                "(:id, 'free', 'Free', '', '{}'::jsonb, '[]'::jsonb, 0, 'active', 0, "
                "now(), now())"
            ),
            {"id": uuid4()},
        )
    sf = SessionFactory(engine)
    app = FastAPI()
    app.include_router(build_router())

    class _Factory:
        def for_session(self, session):  # type: ignore[no-untyped-def]
            from qzdap.modules.platform.adapter.persistence import (
                SqlPlanRepository,
                SqlSubscriptionRepository,
                SqlTenantSettingRepository,
            )

            return PlatformService.from_parts(
                plan_repo=SqlPlanRepository(session),
                subscription_repo=SqlSubscriptionRepository(session),
                setting_repo=SqlTenantSettingRepository(session),
                publisher=None,
            )

    app.state.platform_service_factory = _Factory()
    app.state.container = type("_Container", (), {"session_factory": staticmethod(lambda: sf)})()
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
        headers={
            "X-Tenant-Id": str(_TENANT),
            "X-Workspace-Id": str(_WORKSPACE),
        },
    ) as http:
        yield http
    async with engine.begin() as conn:
        await conn.execute(text(f"DROP SCHEMA {schema} CASCADE"))
    await engine.dispose()


async def test_assigning_a_subscription_actually_persists(client):
    """**写进去就要在库里** ✓（以前返回 200 但库里是空的 ✓）。"""
    resp = await client.put(
        "/v1/platform/subscriptions/me",
        json={"plan_code": "free"},
    )
    assert resp.status_code == 200, resp.text

    rows = await client.get("/v1/platform/subscriptions/me")
    assert rows.status_code == 200, rows.text
    assert rows.json() is not None
    assert rows.json()["plan_code"] == "free"


async def test_updating_an_existing_subscription_does_not_blow_up(client):
    """**第二次写（更新）也必须是 200** ✓ —— 以前是 500 ✓。

    ⚠️ **老坑** ✓ —— ``updated_at`` 是**服务端算的** ✓（``onupdate=func.now()``
    ✓）→ UPDATE 之后 ORM **不知道它的值** ✓ → 属性**过期** ✓ → 域映射读它
    就触发**惰性加载** ✓ → 惰性加载在异步上下文外 → **``MissingGreenlet``**
    ✓✗ → **接口 500** ✓✗。
    → 现在由 mapper 的 ``eager_defaults`` ✓（PostgreSQL 走 RETURNING ✓ ——
    **不多一次往返** ✓）一次性兜住 ✓。
    """
    first = await client.put("/v1/platform/subscriptions/me", json={"plan_code": "free"})
    assert first.status_code == 200, first.text

    second = await client.put("/v1/platform/subscriptions/me", json={"plan_code": "free"})
    assert second.status_code == 200, second.text

    rows = await client.get("/v1/platform/subscriptions/me")
    assert rows.status_code == 200, rows.text
    assert rows.json()["plan_code"] == "free"
