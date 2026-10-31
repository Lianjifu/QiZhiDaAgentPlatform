"""**产物落库 + 下载** —— 真库。

覆盖：

- 落库后能按**四道作用域**取回来 ✓（租户 / 工作区 / 会话 / 属主 ✓）；
- **对不上就当没有** ✓（不是 403 ✓ —— 不告诉调用方「它存在」✓✓）；
- 超过 1 MiB **拒绝** ✓（产物进 SSE 事件流 ✓ → 必须有界 ✓）；
- 下载端点**会话作用域** ✓（四道都对才给内容 ✓）。
"""

from __future__ import annotations

import os
import uuid
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from qzdap.modules.agent_runtime.adapter.http.artifacts import build_artifact_router
from qzdap.modules.agent_runtime.adapter.persistence.artifact_store import (
    PostgresArtifactStore,
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
    rolling_summary text NOT NULL DEFAULT '',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
)
""",
    """
CREATE TABLE "{schema}".session_artifacts (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    session_id uuid NOT NULL,
    owner_id uuid NOT NULL,
    turn_id uuid,
    name varchar(255) NOT NULL,
    kind varchar(16) NOT NULL DEFAULT 'text',
    mime varchar(120) NOT NULL DEFAULT 'text/plain',
    size_bytes integer NOT NULL,
    sha256 varchar(64) NOT NULL,
    snippet text NOT NULL DEFAULT '',
    content bytea NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fk_session_artifacts_session FOREIGN KEY (session_id)
        REFERENCES "{schema}".agent_sessions (id) ON DELETE CASCADE
)
""",
]


@pytest.fixture
async def artifact_ctx():
    url = os.environ.get("QZDAP_TEST_DATABASE_URL")
    if not url:
        pytest.skip("QZDAP_TEST_DATABASE_URL is not set")
    schema = "artifact_" + uuid.uuid4().hex
    admin = create_async_engine(url)
    async with admin.connect() as conn:
        await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        for statement in _DDL:
            await conn.execute(text(statement.replace("{schema}", schema)))
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


async def _session_row(engine, *, session_id: UUID, tenant_id: UUID, owner_id: UUID) -> None:
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO agent_sessions (id, tenant_id, workspace_id, owner_id, "
                " agent_id, agent_version) "
                "VALUES (:id, :tenant_id, :ws, :owner, :agent, 'v1')"
            ),
            {
                "id": session_id,
                "tenant_id": tenant_id,
                "ws": WORKSPACE,
                "owner": owner_id,
                "agent": uuid4(),
            },
        )


TENANT = UUID("00000000-0000-0000-0000-000000000001")
WORKSPACE = UUID("00000000-0000-0000-0000-000000000002")
OWNER = UUID("00000000-0000-0000-0000-000000000010")


@pytest.mark.asyncio
async def test_an_artifact_comes_back_with_its_contents(artifact_ctx) -> None:  # type: ignore[no-untyped-def]
    engine, _schema = artifact_ctx
    session_id = uuid4()
    await _session_row(engine, session_id=session_id, tenant_id=TENANT, owner_id=OWNER)

    async with AsyncSession(engine) as session, session.begin():
        store = PostgresArtifactStore(session)
        record = await store.save(
            tenant_id=TENANT,
            workspace_id=WORKSPACE,
            session_id=session_id,
            owner_id=OWNER,
            turn_id=uuid4(),
            name="周报.md",
            kind="markdown",
            mime="text/markdown",
            content="# 周报\n正文".encode(),
        )

    async with AsyncSession(engine) as session:
        store = PostgresArtifactStore(session)
        found = await store.get(
            tenant_id=TENANT,
            workspace_id=WORKSPACE,
            session_id=session_id,
            owner_id=OWNER,
            artifact_id=record.id,
        )
    assert found is not None
    assert found.content == "# 周报\n正文".encode()
    assert found.snippet == "# 周报\n正文"
    assert found.size_bytes == len("# 周报\n正文".encode())


@pytest.mark.asyncio
async def test_the_scope_must_match_on_all_four(artifact_ctx) -> None:  # type: ignore[no-untyped-def]
    """⚠️ **少一道就当没有** ✓ —— 租户 / 工作区 / 会话 / 属主 ✓。"""
    engine, _schema = artifact_ctx
    session_id = uuid4()
    await _session_row(engine, session_id=session_id, tenant_id=TENANT, owner_id=OWNER)

    async with AsyncSession(engine) as session, session.begin():
        store = PostgresArtifactStore(session)
        record = await store.save(
            tenant_id=TENANT,
            workspace_id=WORKSPACE,
            session_id=session_id,
            owner_id=OWNER,
            turn_id=None,
            name="a.md",
            kind="text",
            mime="text/plain",
            content=b"x",
        )

    async with AsyncSession(engine) as session:
        store = PostgresArtifactStore(session)
        base = {
            "tenant_id": TENANT,
            "workspace_id": WORKSPACE,
            "session_id": session_id,
            "owner_id": OWNER,
            "artifact_id": record.id,
        }
        assert await store.get(**base) is not None
        assert await store.get(**{**base, "tenant_id": uuid4()}) is None
        assert await store.get(**{**base, "workspace_id": uuid4()}) is None
        assert await store.get(**{**base, "session_id": uuid4()}) is None
        assert await store.get(**{**base, "owner_id": uuid4()}) is None


@pytest.mark.asyncio
async def test_more_than_one_mebibyte_is_refused(artifact_ctx) -> None:  # type: ignore[no-untyped-def]
    engine, _schema = artifact_ctx
    session_id = uuid4()
    await _session_row(engine, session_id=session_id, tenant_id=TENANT, owner_id=OWNER)
    async with AsyncSession(engine) as session, session.begin():
        store = PostgresArtifactStore(session)
        with pytest.raises(ValueError):
            await store.save(
                tenant_id=TENANT,
                workspace_id=WORKSPACE,
                session_id=session_id,
                owner_id=OWNER,
                turn_id=None,
                name="big.md",
                kind="text",
                mime="text/plain",
                content=b"x" * (1024 * 1024 + 1),
            )


def _app(engine, *, principal: SimpleNamespace | None) -> FastAPI:
    app = FastAPI()
    app.include_router(build_artifact_router())

    class _SessionFactory:
        def session(self):  # type: ignore[no-untyped-def]
            return AsyncSession(engine)

    class _Container:
        def session_factory(self):  # type: ignore[no-untyped-def]
            return _SessionFactory()

    app.state.container = _Container()

    @app.middleware("http")
    async def _with_principal(request, call_next):  # type: ignore[no-untyped-def]
        request.state.principal = principal
        return await call_next(request)

    return app


@pytest.mark.asyncio
async def test_the_download_needs_the_full_scope(artifact_ctx) -> None:  # type: ignore[no-untyped-def]
    engine, _schema = artifact_ctx
    session_id = uuid4()
    await _session_row(engine, session_id=session_id, tenant_id=TENANT, owner_id=OWNER)
    async with AsyncSession(engine) as session, session.begin():
        store = PostgresArtifactStore(session)
        record = await store.save(
            tenant_id=TENANT,
            workspace_id=WORKSPACE,
            session_id=session_id,
            owner_id=OWNER,
            turn_id=None,
            name="周报.md",
            kind="markdown",
            mime="text/markdown",
            content="# 周报".encode(),
        )

    principal = SimpleNamespace(type="user", tenant_id=TENANT, id=OWNER, workspace_id=WORKSPACE)
    path = f"/api/sessions/{session_id}/artifacts/{record.id}/content"

    async with AsyncClient(
        transport=ASGITransport(app=_app(engine, principal=principal)),
        base_url="http://test",
    ) as client:
        response = await client.get(path, headers={"X-Workspace-Id": str(WORKSPACE)})
        assert response.status_code == 200
        assert response.content == "# 周报".encode()

        # ⚠️ **换个会话就取不到** ✓（产物是会话的输出 ✓）。
        other = await client.get(
            f"/api/sessions/{uuid4()}/artifacts/{record.id}/content",
            headers={"X-Workspace-Id": str(WORKSPACE)},
        )
        assert other.status_code == 404


@pytest.mark.asyncio
async def test_the_download_needs_an_identity(artifact_ctx) -> None:  # type: ignore[no-untyped-def]
    engine, _schema = artifact_ctx
    async with AsyncClient(
        transport=ASGITransport(app=_app(engine, principal=None)),
        base_url="http://test",
    ) as client:
        response = await client.get(f"/api/sessions/{uuid4()}/artifacts/{uuid4()}/content")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_the_mock_artifact_lands_in_the_table(artifact_ctx) -> None:  # type: ignore[no-untyped-def]
    """⚠️ **mock 的产物也进同一张表** ✓ —— 一个下载端点 ✓（不再有 mock 专用路径 ✓）。"""
    from qzdap.modules.agent_runtime.adapter.graph.runner import SessionGraphRunner
    from qzdap.modules.agent_runtime.adapter.llm import LLMPortAdapter
    from qzdap.modules.agent_runtime.domain.catalog import CatalogAgent
    from qzdap_llm.mock import MockLLMClient
    from qzdap_schema.dtos.turn import ArtifactReadyChunk

    engine, _schema = artifact_ctx
    session_id = uuid4()
    await _session_row(engine, session_id=session_id, tenant_id=TENANT, owner_id=OWNER)

    agent = CatalogAgent.create(
        id=uuid4(),
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        name="助手",
        category="企业通用",
        owner="管理员",
        model="demo",
    )
    async with AsyncSession(engine) as session, session.begin():
        runner = SessionGraphRunner(
            llm=LLMPortAdapter(MockLLMClient()),
            artifact_store=PostgresArtifactStore(session),
        )
        chunks = []
        async for chunk in runner.run_graph(
            tenant_id=TENANT,
            workspace_id=WORKSPACE,
            owner_id=OWNER,
            turn_id=uuid4(),
            user_input="给我生成一份周报模板",
            history=[],
            agent=agent,
            model="demo",
            session_id=session_id,
        ):
            chunks.append(chunk)

    cards = [c for c in chunks if isinstance(c, ArtifactReadyChunk)]
    assert len(cards) == 1, "同一轮只发一张卡片"
    card = cards[0]
    assert card.download_path == f"/api/sessions/{session_id}/artifacts/{card.artifact_id}/content"

    async with AsyncSession(engine) as session:
        store = PostgresArtifactStore(session)
        found = await store.get(
            tenant_id=TENANT,
            workspace_id=WORKSPACE,
            session_id=session_id,
            owner_id=OWNER,
            artifact_id=card.artifact_id,
        )
    assert found is not None
    assert found.content
    assert found.name == card.name
