"""HTTP contract regressions for authenticated, user-specific console settings."""
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from qzdap.modules.identity.adapter.http.account_router import build_account_router


def test_account_settings_requires_authenticated_identity():
    app = FastAPI()
    app.include_router(build_account_router())
    response = TestClient(app).get('/api/account/settings', headers={'X-Tenant-Id': str(uuid4())})
    assert response.status_code == 401


def test_invitation_acceptance_requires_authenticated_recipient():
    app = FastAPI()
    app.include_router(build_account_router())
    response = TestClient(app).post(f'/api/workspaces/current/invitations/{uuid4()}/accept')
    assert response.status_code == 401
