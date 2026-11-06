"""开发目录落库测试 —— 三个智能体真的写进库里 ✓。

跑法:``QZDAP_TEST_DATABASE_URL=postgresql+asyncpg://... pytest ...`` ✓
（不设就跳过 ✓）。
"""

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

from qzdap.composition.dev_catalog import AGENT_KEYS, build_assets
from qzdap.modules.agent_runtime.adapter.http.catalog_router import build_catalog_router
from qzdap.modules.agent_runtime.adapter.persistence.catalog_models import CatalogAgentORM
from qzdap.modules.agent_runtime.adapter.persistence.catalog_repositories import (
    SqlCatalogAgentRepository,
)
from qzdap.modules.agent_runtime.application.catalog import AgentCatalogService
from qzdap.modules.identity.adapter.persistence.models import TenantORM, WorkspaceORM
from qzdap.modules.knowledge.adapter.http.router import build_router as knowledge_router
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
from qzdap.modules.orchestration.adapter.http.router import build_router as orchestration_router
from qzdap.modules.orchestration.adapter.persistence.models import (
    WorkflowORM,
    WorkflowRunORM,
    WorkflowUserStateORM,
)
from qzdap.modules.orchestration.adapter.persistence.repositories import (
    SqlWorkflowRepository,
    SqlWorkflowRunRepository,
    SqlWorkflowUserStateRepository,
)
from qzdap.modules.orchestration.application.services import OrchestrationService
from qzdap.modules.platform.adapter.http.ops_mutation_router import build_mutation_router
from qzdap.modules.platform.adapter.http.ops_router import build_ops_router
from qzdap.modules.platform.adapter.persistence.models import AdminOpsDocORM
from qzdap.modules.platform.adapter.persistence.ops_repositories import SqlAdminOpsRepository
from qzdap.modules.platform.application.ops_service import AdminOpsService
from qzdap.modules.skill.adapter.http.router import build_router as skill_router
from qzdap.modules.skill.adapter.persistence.models import SkillORM, SkillUserStateORM
from qzdap.modules.skill.adapter.persistence.repositories import (
    SqlSkillRepository,
    SqlSkillUserStateRepository,
)
from qzdap.modules.skill.application.services import SkillService
from qzdap_http.error_envelope import error_envelope_middleware

TABLES = [
    TenantORM.__table__,
    WorkspaceORM.__table__,
    CatalogAgentORM.__table__,
    SkillORM.__table__,
    SkillUserStateORM.__table__,
    KnowledgeBaseORM.__table__,
    KnowledgeDocORM.__table__,
    KnowledgeChunkORM.__table__,
    KnowledgeSourceORM.__table__,
    KnowledgeDocUserStateORM.__table__,
    WorkflowORM.__table__,
    WorkflowUserStateORM.__table__,
    WorkflowRunORM.__table__,
    AdminOpsDocORM.__table__,
]


@pytest.fixture
async def catalog_db():
    url = os.environ.get("QZDAP_TEST_DATABASE_URL")
    if not url:
        pytest.skip("QZDAP_TEST_DATABASE_URL is not set")
    engine = create_async_engine(url)
    schema = "dev_catalog_" + uuid4().hex
    async with engine.connect() as connection:
        transaction = await connection.begin()
        await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        await connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
        for table in TABLES:
            await connection.run_sync(lambda conn, table=table: table.create(conn))

        @asynccontextmanager
        async def session():
            async with AsyncSession(
                bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
            ) as db:
                yield db

        tenant, workspace = uuid4(), uuid4()
        async with session() as db:
            db.add(
                TenantORM(
                    id=tenant,
                    tenant_id=tenant,
                    slug=f"t-{tenant.hex[:8]}",
                    display_name="目录测试租户",
                    status="active",
                )
            )
            db.add(
                WorkspaceORM(
                    id=workspace,
                    tenant_id=tenant,
                    slug=f"w-{workspace.hex[:8]}",
                    display_name="目录测试工作区",
                    status="active",
                )
            )
            await db.commit()

        app = FastAPI()
        app.state.container = SimpleNamespace(
            session_factory=lambda: SimpleNamespace(session=session)
        )
        app.state.agent_catalog_factory = SimpleNamespace(
            for_session=lambda db: AgentCatalogService(SqlCatalogAgentRepository(db))
        )
        app.state.skill_factory = SimpleNamespace(
            for_session=lambda db: SkillService(
                skills=SqlSkillRepository(db),
                user_state=SqlSkillUserStateRepository(db),
            )
        )
        app.state.knowledge_service_factory = SimpleNamespace(
            for_session=lambda db: KnowledgeService(
                SqlKnowledgeCatalogRepository(db),
                embedding=None,
                vectors=None,
                user_state=SqlKnowledgeDocUserStateRepository(db),
            )
        )
        app.state.orchestration_service_factory = SimpleNamespace(
            for_session=lambda db: OrchestrationService(
                workflows=SqlWorkflowRepository(db),
                user_state=SqlWorkflowUserStateRepository(db),
                runs=SqlWorkflowRunRepository(db),
            )
        )
        app.state.admin_ops_factory = SimpleNamespace(
            for_session=lambda db: AdminOpsService(SqlAdminOpsRepository(db))
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
        app.include_router(skill_router())
        app.include_router(knowledge_router())
        app.include_router(orchestration_router())
        app.include_router(build_ops_router())
        app.include_router(build_mutation_router())
        app.middleware("http")(error_envelope_middleware)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            yield client, session, tenant, workspace
        await transaction.rollback()
    await engine.dispose()


async def test_catalog_lands_through_the_real_api(catalog_db) -> None:
    client, _sessions, tenant, workspace = catalog_db
    headers = {"X-Tenant-Id": str(tenant), "X-Workspace-Id": str(workspace)}

    for asset in build_assets():
        resp = await client.post(asset.path, json=asset.payload, headers=headers)
        assert resp.status_code < 400, f"{asset.kind}/{asset.key}: {resp.text[:300]}"

    agents = (await client.get("/api/admin/agents", headers=headers)).json()
    names = [item["name"] for item in agents]
    assert "办公智能体" in names
    assert "招聘智能体" in names
    assert "调研智能体" in names

    office = next(item for item in agents if item["name"] == "办公智能体")
    assert office["status"] == "published"
    assert office["category"] == "办公协同"
    assert len(office["tools"]) == 3
    assert len(office["knowledgeRefs"]) == 2
    assert len(office["flowRefs"]) == 2
    assert office["prompts"]["prompt"].strip()
    assert office["memoryPolicy"]["enabled"] is True

    skills = (await client.get("/api/admin/skills", headers=headers)).json()
    skill_ids = {item["id"] for item in skills}
    skill_names = {item["name"] for item in skills}
    assert {"日程助手", "会议纪要生成", "文档摘要"} <= skill_names
    assert {"简历解析", "JD 生成", "面试排期"} <= skill_names
    assert {"竞品检索", "竞品对比分析", "调研报告生成"} <= skill_names
    for agent in agents:
        for tool in agent["tools"]:
            assert tool["id"] in skill_ids, f"{agent['name']} 绑了不存在的技能"

    kbs = (await client.get("/api/admin/knowledge/kbs", headers=headers)).json()
    kb_ids = {item["id"] for item in kbs}
    kb_names = {item["name"] for item in kbs}
    assert {
        "员工手册",
        "会议纪要库",
        "岗位说明书库",
        "面试题库",
        "行业报告库",
        "竞品资料库",
    } <= kb_names
    assert all(item["docCount"] > 0 for item in kbs), "每个知识库都要有文档"
    for agent in agents:
        for ref in agent["knowledgeRefs"]:
            assert ref["id"] in kb_ids, f"{agent['name']} 绑了不存在的知识库"

    docs = (await client.get("/api/admin/knowledge/docs", headers=headers)).json()
    assert len(docs) == 13
    assert all(doc["chunks"] >= 1 for doc in docs)
    assert all(doc["chunksPreview"] for doc in docs)

    flows = (await client.get("/api/admin/workflows", headers=headers)).json()
    flow_ids = {item["id"] for item in flows}
    assert len(flows) == 6
    assert all(item["initialNodes"] for item in flows)
    for agent in agents:
        for ref in agent["flowRefs"]:
            assert ref["id"] in flow_ids, f"{agent['name']} 绑了不存在的工作流"

    suites = (await client.get("/api/admin/evaluations/suites", headers=headers)).json()
    assert len(suites) == len(AGENT_KEYS)
    agent_ids = {item["id"] for item in agents}
    for suite in suites:
        assert suite["target"] in agent_ids
        assert suite["casesList"]


async def test_catalog_seed_is_idempotent(catalog_db) -> None:
    """同一批资产重复写 —— 不产生第二份 ✓（id 确定性 ✓）。"""
    client, _sessions, tenant, workspace = catalog_db
    headers = {"X-Tenant-Id": str(tenant), "X-Workspace-Id": str(workspace)}
    assets = build_assets()

    for asset in assets:
        resp = await client.post(asset.path, json=asset.payload, headers=headers)
        assert resp.status_code < 400, f"{asset.kind}/{asset.key}: {resp.text[:300]}"

    agents = (await client.get("/api/admin/agents", headers=headers)).json()
    assert len(agents) == len(AGENT_KEYS)
    skills = (await client.get("/api/admin/skills", headers=headers)).json()
    assert len(skills) == 9
    kbs = (await client.get("/api/admin/knowledge/kbs", headers=headers)).json()
    assert len(kbs) == 6
    flows = (await client.get("/api/admin/workflows", headers=headers)).json()
    assert len(flows) == 6
