"""Model import/health routes execute real SQL repositories in disposable schema."""
from __future__ import annotations
import os
from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import uuid4
import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from qzdap.modules.model.adapter.http.router import build_router
from qzdap.modules.model.adapter.persistence.models import CatalogModelORM, ProviderORM, RouteORM, HealthEventORM
from qzdap.modules.model.adapter.persistence.repositories import SqlModelRepository, SqlProviderRepository, SqlRouteRepository, SqlHealthRepository
from qzdap.modules.model.application.services import ModelService
from qzdap.modules.model.domain.entities import Provider

class Cipher:
    def encrypt(self, value, *, aad=None): return value
    def decrypt(self, value, *, aad=None): return value

class Tester:
    __test__ = False
    def __init__(self): self.calls = []
    async def test_connection(self, **kwargs):
        self.calls.append(kwargs)
        return {"success": True, "response": "live provider output"}

async def test_model_import_and_health_route_persist_scoped_data():
    url = os.environ.get("QZDAP_TEST_DATABASE_URL")
    if not url: pytest.skip("QZDAP_TEST_DATABASE_URL is not set")
    engine = create_async_engine(url)
    async with engine.connect() as connection:
        transaction = await connection.begin()
        schema = "model_contract_" + uuid4().hex
        await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        await connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
        for table in [ProviderORM.__table__, CatalogModelORM.__table__, RouteORM.__table__, HealthEventORM.__table__]:
            await connection.run_sync(lambda c, table=table: table.create(c))
        @asynccontextmanager
        async def sessions():
            async with AsyncSession(bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint") as session:
                yield session
        tenant, workspace, provider_id, actor_id = uuid4(), uuid4(), uuid4(), uuid4()
        async with sessions() as session:
            await SqlProviderRepository(session).add(Provider.create(id=provider_id, tenant_id=tenant,
                workspace_id=workspace, name="saved provider", base_url="https://provider.test/v1", protocol="openai", api_key_masked="masked", encrypted_payload=b"key"))
            await session.commit()
        tester = Tester()
        def service(session):
            return ModelService(SqlModelRepository(session), SqlProviderRepository(session), SqlRouteRepository(session), SqlHealthRepository(session), cipher=Cipher(), connectivity_tester=tester)
        app = FastAPI()
        app.state.container = SimpleNamespace(session_factory=lambda: SimpleNamespace(session=sessions))
        app.state.model_service_factory = SimpleNamespace(for_session=service)
        @app.middleware("http")
        async def principal(request, call_next):
            request.state.principal = SimpleNamespace(id=actor_id, tenant_id=tenant, workspace_id=workspace, roles=["admin"], display_name="admin")
            return await call_next(request)
        app.include_router(build_router())
        headers = {"X-Tenant-Id": str(tenant), "X-Workspace-Id": str(workspace)}
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            import json
            response = await client.post("/api/admin/models/import", headers=headers, json={"format": "json", "content": json.dumps([{"name": "imported", "providerId": str(provider_id), "upstreamModel": "provider-model"}])})
            assert response.status_code == 200, response.text
            assert response.json()["created"] == 1
            health = await client.post(f"/api/admin/models/providers/{provider_id}/health-check", headers=headers)
            assert health.status_code == 200, health.text
            assert tester.calls[0]["api_key"] == "key"
            assert tester.calls[0]["model"] == "provider-model"
            assert health.json()["success"] is True
            denied = await client.post(f"/api/admin/models/providers/{provider_id}/health-check", headers={**headers, "X-Workspace-Id": str(uuid4())})
            assert denied.status_code == 403
            assert len(tester.calls) == 1
        async with sessions() as session:
            models = list((await session.execute(select(CatalogModelORM))).scalars())
            events = list((await session.execute(select(HealthEventORM))).scalars())
            assert models[0].name == "imported"
            assert models[0].upstream_model == "provider-model"
            assert models[0].status == "draft"
            assert events[0].provider_id == provider_id
            assert events[0].message == "live provider output"
        await transaction.rollback()
    await engine.dispose()
