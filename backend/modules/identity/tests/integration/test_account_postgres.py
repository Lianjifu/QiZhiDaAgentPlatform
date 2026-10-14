"""Real PostgreSQL and JWT HTTP roundtrips in a disposable schema."""
from __future__ import annotations

import importlib.util
import os
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient
from qzdap_auth.jwt import JWTConfig, JWTIssuer, JWTVerifier
from qzdap_auth.middleware import AuthMiddleware
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from qzdap.modules.agent_runtime.adapter.http.attachments import (
    build_attachment_router,
    resolve_attachment_context,
)
from qzdap.modules.agent_runtime.adapter.persistence.attachment_models import CopilotAttachmentORM
from qzdap.modules.agent_runtime.adapter.persistence.models import SessionORM, TurnORM
from qzdap.modules.identity.adapter.http.account_router import build_account_router
from qzdap.modules.identity.adapter.persistence.control_models import (
    IdentityControlAuditORM,
    WorkspaceInvitationORM,
)
from qzdap.modules.identity.adapter.persistence.models import UserORM, UserWorkspaceORM, WorkspaceORM
from qzdap.modules.platform.adapter.http.router import (
    build_router as platform_router,
    platform_service_dependency,
)
from qzdap.modules.platform.adapter.persistence.models import TenantSettingORM


@pytest.fixture
async def database_console():
    dsn = os.environ.get('QZDAP_TEST_DATABASE_URL')
    if not dsn:
        pytest.skip('set QZDAP_TEST_DATABASE_URL for isolated PostgreSQL integration')
    schema = 'identity_test_' + uuid4().hex
    engine = create_async_engine(dsn, connect_args={'server_settings': {'search_path': schema}})
    try:
        async with engine.begin() as connection:
            await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            for model in (WorkspaceORM, UserORM, UserWorkspaceORM, SessionORM, TurnORM, TenantSettingORM):
                # Some shared model helpers generate generic index names such
                # as ix_tenant_id_status. PostgreSQL index names are schema
                # global, so qualify these names in this isolated schema.
                for index in model.__table__.indexes:
                    if index.name and index.name.startswith("ix_tenant_id"):
                        index.name = f"{model.__tablename__}_{index.name}"
                await connection.run_sync(model.__table__.create)
            migration_path = Path(__file__).resolve().parents[4] / 'migrations/versions/0034_identity_control.py'
            spec = importlib.util.spec_from_file_location('identity_test_migration', migration_path)
            migration = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(migration)
            def run_migration(conn):
                with Operations.context(MigrationContext.configure(conn)):
                    migration.upgrade()
            await connection.run_sync(run_migration)
        maker = async_sessionmaker(engine, expire_on_commit=False)
        tenant, other_tenant, workspace, other_workspace, admin, member, outsider = (uuid4() for _ in range(7))
        runtime_session = uuid4()
        async with maker.begin() as session:
            session.add_all([
                WorkspaceORM(id=workspace, tenant_id=tenant, slug='main', display_name='Main'),
                WorkspaceORM(id=other_workspace, tenant_id=tenant, slug='second', display_name='Second'),
                UserORM(id=admin, tenant_id=tenant, email='admin@example.com', display_name='Admin', metadata_={'keep': 'yes'}),
                UserORM(id=member, tenant_id=tenant, email='member@example.com', display_name='Member'),
                UserORM(id=outsider, tenant_id=other_tenant, email='outsider@example.com', display_name='Other tenant'),
            ])
            await session.flush()
            session.add_all([
                UserWorkspaceORM(id=uuid4(), tenant_id=tenant, user_id=admin, workspace_id=workspace, role='admin'),
                UserWorkspaceORM(id=uuid4(), tenant_id=tenant, user_id=admin, workspace_id=other_workspace, role='admin'),
                SessionORM(id=runtime_session, tenant_id=tenant, workspace_id=workspace, owner_id=admin, agent_id=uuid4(), agent_version='v1'),
            ])
        class SessionFactory:
            @asynccontextmanager
            async def session(self):
                async with maker() as session:
                    yield session
        app = FastAPI()
        app.state.container = SimpleNamespace(session_factory=lambda: SessionFactory())
        app.include_router(build_account_router())
        app.include_router(build_attachment_router())
        app.include_router(platform_router())
        # The tested settings handler uses the identity DB transaction; its
        # legacy service dependency is retained for the other platform routes.
        app.dependency_overrides[platform_service_dependency] = lambda: None
        config = JWTConfig(secret='integration-test-secret-64-characters-' + 'x' * 30)
        issuer = JWTIssuer(config)
        app.add_middleware(AuthMiddleware, verifier=JWTVerifier(config))
        def headers(user=admin, scope=workspace, tid=tenant, roles=frozenset({'admin'})):
            token, _ = issuer.issue_access_token(principal_id=user, tenant_id=tid, workspace_id=scope, roles=roles)
            return {'Authorization': 'Bearer ' + token, 'X-Tenant-Id': str(tid), 'X-Workspace-Id': str(scope), 'X-User-Id': str(user)}
        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
            yield SimpleNamespace(client=client, maker=maker, headers=headers, tenant=tenant, other_tenant=other_tenant, workspace=workspace, other_workspace=other_workspace, admin=admin, member=member, outsider=outsider, runtime_session=runtime_session)
    finally:
        async with engine.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await engine.dispose()


async def test_account_updates_actual_user_and_isolates_users_and_workspaces(database_console):
    db = database_console
    client, headers = db.client, db.headers
    response = await client.put('/api/account/settings', headers=headers(), json={'displayName': 'New Admin', 'email': 'ADMIN@example.com', 'language': 'en-US', 'digest': True, 'taskAlert': True})
    assert response.status_code == 200, response.text
    assert response.json()['email'] == 'admin@example.com'
    assert (await client.get('/api/account/settings', headers=headers(scope=db.other_workspace))).json()['digest'] is True
    other = await client.get('/api/account/settings', headers=headers(user=db.member, roles=frozenset()))
    assert other.status_code == 200
    assert other.json()['displayName'] == 'Member'
    assert other.json()['digest'] is False
    duplicate = await client.put('/api/account/settings', headers=headers(), json={'displayName': 'Duplicate', 'email': 'member@example.com'})
    assert duplicate.status_code == 409
    spoofed = headers()
    spoofed['X-User-Id'] = str(db.member)
    assert (await client.get('/api/account/settings', headers=spoofed)).status_code == 403
    async with db.maker() as session:
        row = await session.get(UserORM, db.admin)
        assert row.metadata_['keep'] == 'yes'
        assert row.metadata_['accountSettings']['language'] == 'en-US'
        assert row.display_name == 'New Admin'
        assert (await session.scalars(select(IdentityControlAuditORM))).all()[0].action == 'account.settings.updated'


async def test_pending_invite_acceptance_creates_real_membership_only_for_recipient(database_console):
    db = database_console
    client = db.client
    body = {'email': 'member@example.com', 'role': '成员', 'team': 'Finance'}
    response = await client.post('/api/workspaces/current/members/invite', headers=db.headers(), json=body)
    assert response.status_code == 201, response.text
    invitation = response.json()
    assert invitation['status'] == 'pending'
    assert invitation['deliveryStatus'] == 'not_configured'
    before = (await client.get('/api/workspaces/current/members', headers=db.headers())).json()
    assert len(before) == 1 and before[0]['id'] == str(db.admin)
    assert (await client.post('/api/workspaces/current/members/invite', headers=db.headers(), json=body)).status_code == 409
    path = f"/api/workspaces/current/invitations/{invitation['id']}/accept"
    assert (await client.post(path, headers=db.headers())).status_code == 404
    accepted = await client.post(path, headers=db.headers(user=db.member, roles=frozenset()))
    assert accepted.status_code == 200, accepted.text
    after = (await client.get('/api/workspaces/current/members', headers=db.headers())).json()
    assert {row['id'] for row in after} == {str(db.admin), str(db.member)}
    assert (await client.post('/api/workspaces/current/members/invite', headers=db.headers(user=db.member, roles=frozenset()), json={'email': 'third@example.com'})).status_code == 403
    assert (await client.get('/api/workspaces/current/members', headers=db.headers(scope=db.other_workspace))).json()[0]['id'] == str(db.admin)
    async with db.maker() as session:
        assert (await session.get(WorkspaceInvitationORM, __import__('uuid').UUID(invitation['id']))).status == 'accepted'


async def test_platform_settings_and_audit_commit_together(database_console):
    db = database_console
    response = await db.client.put('/v1/platform/settings/console', headers=db.headers(), json={'value': {'brandName': 'Company'}})
    assert response.status_code == 200, response.text
    assert response.json()['value']['brandName'] == 'Company'
    response = await db.client.get('/api/admin/settings/audit', headers=db.headers())
    assert response.status_code == 200, response.text
    assert response.json()[0]['action'] == 'platform.settings.console'
    assert response.json()[0]['actor'] == 'Admin'
    async with db.maker() as session:
        settings = (await session.scalars(select(TenantSettingORM))).all()
        audits = (await session.scalars(select(IdentityControlAuditORM))).all()
        assert len(settings) == len(audits) == 1
        assert settings[0].updated_by == db.admin
        assert audits[0].payload == {'key': 'console', 'before': None, 'after': {'brandName': 'Company'}}
    denied = await db.client.put('/v1/platform/settings/console', headers=db.headers(user=db.member, roles=frozenset()), json={'value': {'brandName': 'Forged'}})
    assert denied.status_code == 403


async def test_insights_count_owner_workspace_real_turns_only(database_console):
    db = database_console
    now = datetime.now(UTC)
    async with db.maker.begin() as session:
        member_session = uuid4()
        session.add(SessionORM(id=member_session, tenant_id=db.tenant, workspace_id=db.workspace, owner_id=db.member, agent_id=uuid4(), agent_version='v1'))
        await session.flush()
        session.add_all([
            TurnORM(id=uuid4(), tenant_id=db.tenant, workspace_id=db.workspace, session_id=db.runtime_session, user_input='actual success', status='succeeded', started_at=now - timedelta(hours=2)),
            TurnORM(id=uuid4(), tenant_id=db.tenant, workspace_id=db.workspace, session_id=db.runtime_session, user_input='actual failure', status='failed', started_at=now - timedelta(hours=1)),
            TurnORM(id=uuid4(), tenant_id=db.tenant, workspace_id=db.workspace, session_id=member_session, user_input='another user', status='succeeded', started_at=now - timedelta(hours=1)),
            TurnORM(id=uuid4(), tenant_id=db.tenant, workspace_id=db.workspace, session_id=db.runtime_session, user_input='old turn', status='succeeded', started_at=now - timedelta(days=40)),
        ])
    response = await db.client.get('/api/home/insights', headers=db.headers(), params={'range': '近 7 天'})
    assert response.status_code == 200, response.text
    data = response.json()
    assert sum(point['tasks'] for point in data['points']) == 1
    assert {row['title'] for row in data['outcomes']} == {'actual success', 'actual failure'}
    assert 'savedHours' not in data
    empty = await db.client.get('/api/home/insights', headers=db.headers(scope=db.other_workspace))
    assert empty.json()['points'] == []


async def test_attachments_persist_exact_bytes_and_resolve_owned_turn_context(database_console):
    db = database_console
    content = '真实文档 content\n'.encode()
    path = f'/api/sessions/{db.runtime_session}/attachments'
    response = await db.client.post(path, headers=db.headers(), files={'file': ('report.md', content, 'text/markdown')})
    assert response.status_code == 201, response.text
    attachment = response.json()
    download = await db.client.get(path + '/' + attachment['id'], headers=db.headers())
    assert download.status_code == 200 and download.content == content
    denied = await db.client.get(path + '/' + attachment['id'], headers=db.headers(user=db.member, roles=frozenset()))
    assert denied.status_code == 404
    async with db.maker() as session:
        stored = await session.get(CopilotAttachmentORM, __import__('uuid').UUID(attachment['id']))
        assert stored.content == content and stored.size_bytes == len(content)
        request = Request({'type': 'http', 'headers': [(k.lower().encode(), v.encode()) for k, v in db.headers().items()], 'state': {'principal': __import__('qzdap_kernel.principal', fromlist=['Principal']).Principal(id=db.admin, type=__import__('qzdap_kernel.principal', fromlist=['PrincipalType']).PrincipalType.USER, tenant_id=db.tenant, workspace_id=db.workspace)}})
        result = await resolve_attachment_context(session, request, db.runtime_session, f"summarize [附件: report.md, ID: {attachment['id']}]")
        assert content.decode() in result
        assert 'untrusted data' in result
    binary = await db.client.post(path, headers=db.headers(), files={'file': ('report.pdf', b'%PDF', 'application/pdf')})
    assert binary.status_code == 415
    too_big = await db.client.post(path, headers=db.headers(), files={'file': ('large.txt', b'x' * (1024 * 1024 + 1), 'text/plain')})
    assert too_big.status_code == 413
