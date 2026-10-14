"""HTTP contracts exercise the real SQL repository in an isolated PostgreSQL schema."""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from qzdap.modules.platform.adapter.http.ops_router import build_ops_router, ops_dependency
from qzdap.modules.platform.adapter.persistence.models import AdminOpsDocORM
from qzdap.modules.platform.adapter.persistence.ops_repositories import SqlAdminOpsRepository
from qzdap.modules.platform.application.ops_service import AdminOpsService


@pytest.fixture
async def client():
    dsn = os.environ.get('QZDAP_TEST_DATABASE_URL')
    if not dsn:
        pytest.skip('set QZDAP_TEST_DATABASE_URL to run PostgreSQL HTTP roundtrips')
    schema = f'ops_test_{uuid4().hex}'
    engine = create_async_engine(dsn, connect_args={'server_settings': {'search_path': schema}})
    async with engine.begin() as conn:
        await conn.execute(text(f'CREATE SCHEMA {schema}'))
        await conn.run_sync(AdminOpsDocORM.__table__.create)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    app = FastAPI()
    app.include_router(build_ops_router())
    async def provide():
        async with maker() as session:
            try:
                yield AdminOpsService(SqlAdminOpsRepository(session))
                await session.commit()
            except Exception:
                await session.rollback()
                raise
    app.dependency_overrides[ops_dependency] = provide
    async with AsyncClient(transport=ASGITransport(app=app, raise_app_exceptions=False), base_url='http://test', headers={'X-Tenant-Id': str(uuid4()), 'X-Workspace-Id': str(uuid4())}) as http:
        yield http
    async with engine.begin() as conn:
        await conn.execute(text(f'DROP SCHEMA {schema} CASCADE'))
    await engine.dispose()


async def test_suite_crud_import_and_bulk_delete(client):
    imported = await client.post('/api/admin/evaluations/suites/import', json={'content': '[{"name":"alpha"},{"name":"beta"}]', 'format': 'json'})
    assert imported.status_code == 200, imported.text
    rows = (await client.get('/api/admin/evaluations/suites')).json()
    assert {row['name'] for row in rows} == {'alpha', 'beta'}
    patched = await client.patch(f"/api/admin/evaluations/suites/{rows[0]['id']}", json={'starred': True})
    assert patched.status_code == 200, patched.text
    assert patched.json()['starred'] is True
    deleted = await client.request('DELETE', '/api/admin/evaluations/suites/bulk-delete', json={'ids': [row['id'] for row in rows]})
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()['deleted'] == 2
    assert (await client.get('/api/admin/evaluations/suites')).json() == []


async def test_history_reply_and_workspace_isolation(client):
    imported = await client.post('/api/admin/feedback/import', json={'content': '[{"id":"fb-a","comment":"need help","status":"new"}]', 'format': 'json'})
    assert imported.status_code == 200, imported.text
    response = await client.post('/api/admin/feedback/fb-a/reply', json={'reply': '已处理'})
    assert response.status_code == 200, response.text
    assert response.json()['reply'] == '已处理'
    history = await client.get('/api/admin/feedback/fb-a/history')
    assert history.status_code == 200, history.text
    assert history.json()[-1]['action'] == 'patch'
    hidden = await client.get('/api/admin/feedback/list', headers={'X-Workspace-Id': str(uuid4())})
    assert hidden.json() == []
    missing = await client.patch('/api/admin/feedback/fb-missing', json={'status': 'resolved'})
    assert missing.status_code == 404


async def test_invalid_import_is_atomic_and_422(client):
    response = await client.post('/api/admin/feedback/import', json={'content': '[{"comment":"ok"}, 7]', 'format': 'json'})
    assert response.status_code == 422, response.text
    assert (await client.get('/api/admin/feedback/list')).json() == []


async def test_incidents_batch_uses_session_ids_and_boolean_field(client):
    # Persist through the same service used by import; use channels as a scoped seed route
    # then import incident documents through the dedicated import endpoint.
    response = await client.post('/api/admin/operations/incidents/import', json={'content': '[{"id":"inc-a","sessionId":"session-a","resolved":false}]', 'format': 'json'})
    assert response.status_code == 200, response.text
    response = await client.post('/api/admin/operations/incidents/batch-resolve', json={'sessionIds': ['session-a']})
    assert response.status_code == 200, response.text
    assert response.json()['updated'] == 1
    assert (await client.get('/api/admin/operations/incidents')).json()[0]['resolved'] is True


async def test_run_requires_real_cases_and_executor(client):
    created = (await client.post('/api/admin/evaluations/suites', json={'name': 'suite', 'target': 'agent'})).json()
    response = await client.post(f"/api/admin/evaluations/suites/{created['id']}/run", headers={'X-User-Id': str(uuid4())})
    assert response.status_code == 422, response.text
    row = (await client.get('/api/admin/evaluations/suites')).json()[0]
    assert row['lastRunAt'] == '未运行'
