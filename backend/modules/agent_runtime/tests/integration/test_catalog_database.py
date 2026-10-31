"""Catalog HTTP -> real repository -> PostgreSQL regressions in isolated schemas."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from qzdap.modules.agent_runtime.adapter.http.catalog_router import build_catalog_router
from qzdap.modules.agent_runtime.adapter.persistence.catalog_models import CatalogAgentORM
from qzdap.modules.agent_runtime.adapter.persistence.catalog_repositories import (
    SqlCatalogAgentRepository,
)
from qzdap.modules.agent_runtime.application.catalog import AgentCatalogService
from qzdap.modules.identity.adapter.persistence.models import TenantORM, WorkspaceORM
from qzdap.modules.memory.adapter.http.router import build_router as memory_router
from qzdap.modules.memory.adapter.persistence.models import MemoryPolicyORM
from qzdap.modules.memory.adapter.persistence.repositories import SqlMemoryCatalogRepository
from qzdap.modules.memory.application.admin_service import MemoryAdminService
from qzdap.modules.memory.application.services import MemoryRuntimeService


@pytest.fixture
async def catalog_db():
    url = os.environ.get("QZDAP_TEST_DATABASE_URL")
    if not url:
        pytest.skip("QZDAP_TEST_DATABASE_URL is not set")
    engine = create_async_engine(url)
    schema = "catalog_contract_" + uuid4().hex
    async with engine.connect() as connection:
        transaction = await connection.begin()
        await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        await connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
        # ⚠️ **身份表的租户 / 工作区** ✓ —— 请求链路会**校验工作区存在且 active**
        # ✓（workspace guard ✓）→ 一次性 schema 里没有这两张表就报
        # 「relation workspaces does not exist」✓。
        for table in [
            TenantORM.__table__,
            WorkspaceORM.__table__,
            CatalogAgentORM.__table__,
            MemoryPolicyORM.__table__,
        ]:
            await connection.run_sync(lambda conn, table=table: table.create(conn))

        @asynccontextmanager
        async def session():
            async with AsyncSession(
                bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
            ) as db:
                yield db

        tenant, workspace = uuid4(), uuid4()
        # ⚠️ **租户与工作区得先在** ✓（workspace guard ✓ —— 没有这两行就是
        # `WORKSPACE_NOT_FOUND` ✓）。
        async with session() as db:
            db.add(
                TenantORM(
                    id=tenant,
                    tenant_id=tenant,
                    slug=f"t-{tenant.hex[:8]}",
                    display_name="测试租户",
                    status="active",
                )
            )
            db.add(
                WorkspaceORM(
                    id=workspace,
                    tenant_id=tenant,
                    slug=f"w-{workspace.hex[:8]}",
                    display_name="测试工作区",
                    status="active",
                )
            )
            await db.commit()
        app = FastAPI()
        app.state.container = SimpleNamespace(
            session_factory=lambda: SimpleNamespace(session=session)
        )

        async def evaluator(**kwargs):
            return "real execution response"

        app.state.agent_catalog_factory = SimpleNamespace(
            for_session=lambda db: AgentCatalogService(
                SqlCatalogAgentRepository(db), evaluator=evaluator
            )
        )
        app.state.memory_runtime_service_factory = SimpleNamespace(
            for_session=lambda db: MemoryRuntimeService(SqlMemoryCatalogRepository(db))
        )
        # ⚠️ 管理端走**管理面**的工厂 ✓（平面分离 ✓ —— Memory Stage 0 ✓）。
        app.state.memory_admin_service_factory = SimpleNamespace(
            for_session=lambda db: MemoryAdminService(SqlMemoryCatalogRepository(db))
        )

        @app.middleware("http")
        async def principal(request, call_next):
            request.state.principal = SimpleNamespace(
                tenant_id=tenant,
                workspace_id=UUID(request.headers.get("X-Workspace-Id", str(workspace))),
                id=uuid4(),
            )
            return await call_next(request)

        app.include_router(build_catalog_router())
        app.include_router(memory_router())
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            yield client, session, tenant, workspace
        await transaction.rollback()
    await engine.dispose()


async def test_catalog_version_and_execution_http_persist(catalog_db):
    client, sessions, tenant, workspace = catalog_db
    headers = {"X-Tenant-Id": str(tenant), "X-Workspace-Id": str(workspace)}
    response = await client.post(
        "/api/admin/agents",
        headers=headers,
        json={"name": "snapshot-agent", "status": "published", "prompts": {"prompt": "first"}},
    )
    assert response.status_code == 201, response.text
    aid = response.json()["id"]
    base = f"/api/admin/agents/{aid}"
    for patch in [{"status": "draft", "prompts": {"prompt": "second"}}, {"status": "published"}]:
        assert (await client.patch(base, headers=headers, json=patch)).status_code == 200
    diff = await client.post(
        "/api/admin/agents/diff",
        headers=headers,
        json={"agentId": aid, "leftVersion": "v1", "rightVersion": "v2"},
    )
    assert diff.json()["changes"]["prompts"]["before"]["prompt"] == "first"
    rollback = await client.post(base + "/rollback", headers=headers, json={"version": "v1"})
    assert rollback.status_code == 200
    assert rollback.json()["version"] == "v3"
    assert rollback.json()["prompts"]["prompt"] == "first"
    evaluation = await client.post(
        base + "/eval",
        headers=headers,
        json={"cases": [{"input": "question", "expected": "response"}]},
    )
    assert evaluation.status_code == 200, evaluation.text
    assert evaluation.json()["passRate"] == 1
    history = await client.get(base + "/evaluations", headers=headers)
    assert len(history.json()["runs"]) == 1
    audit = await client.get(base + "/audit", headers=headers)
    assert any(a["action"] == "回滚版本" for a in audit.json())
    exported = await client.post(
        "/api/admin/agents/export", headers=headers, json={"ids": [aid], "format": "json"}
    )
    assert exported.status_code == 200, exported.text
    assert exported.json()[0]["prompts"]["prompt"] == "first"
    async with sessions() as db:
        stored = await db.get(CatalogAgentORM, UUID(aid))
        assert stored.versions[0]["rollbackOf"] == "v1"
        assert stored.audit_events[-1]["run"]["passRate"] == 1
    foreign = await client.patch(
        base, headers={**headers, "X-Workspace-Id": str(uuid4())}, json={"name": "foreign"}
    )
    assert foreign.status_code == 404


async def test_memory_relationships_are_saved_explicit_references(catalog_db):
    """**agent ↔ 保留策略的绑定要落库并查得到** ✓。

    ⚠️ **不再有 L3 关联** ✓ —— L3 退役 ✓（决策 #1 ✓ —— M-47 ✓）→
    团队知识归 **knowledge** ✓（这条链路查的是**保留策略** ✓）。
    """
    client, sessions, tenant, workspace = catalog_db
    async with sessions() as db:
        db.add(
            MemoryPolicyORM(tenant_id=tenant, workspace_id=workspace, label="长期记忆", layer="l2")
        )
        await db.commit()
    headers = {"X-Tenant-Id": str(tenant), "X-Workspace-Id": str(workspace)}
    response = await client.post(
        "/api/admin/agents",
        headers=headers,
        json={
            "name": "memory-agent",
            "memoryPolicy": {"enabled": True, "scope": "user", "policyLabel": "长期记忆"},
        },
    )
    aid = response.json()["id"]
    policy = await client.get("/api/admin/memory/policies/长期记忆/agents", headers=headers)
    assert policy.status_code == 200, policy.text
    assert [a["id"] for a in policy.json()] == [aid]
    foreign = await client.get(
        "/api/admin/memory/policies/长期记忆/agents",
        headers={**headers, "X-Workspace-Id": str(uuid4())},
    )
    assert foreign.status_code == 404
