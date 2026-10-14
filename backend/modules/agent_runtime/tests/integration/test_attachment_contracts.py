"""Attachment route must reject unsupported input before it claims persistence."""
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from qzdap.modules.agent_runtime.adapter.http.session_router import build_session_router


def test_attachment_upload_requires_authenticated_identity():
    app = FastAPI()
    app.include_router(build_session_router())
    response = TestClient(app).post(f'/api/sessions/{uuid4()}/attachments', files={'file': ('report.txt', b'real bytes', 'text/plain')})
    assert response.status_code == 401
