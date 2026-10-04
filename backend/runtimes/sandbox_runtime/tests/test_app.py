"""Unit tests for sandbox_runtime jobs API (stub executor)."""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from qzdap.runtimes.sandbox_runtime.app import create_app
from qzdap.runtimes.sandbox_runtime.executor import (
    StubExecutor,
    clip_output,
    safe_relpath,
)
from qzdap.runtimes.sandbox_runtime.settings import Settings

SECRET = "test-sandbox-secret"


def _app(executor: StubExecutor | None = None) -> TestClient:
    settings = Settings(
        sandbox_executor="stub",
        sandbox_runtime_secret=SECRET,
        sandbox_images="qzdap/sandbox-python:latest",
        env="test",
    )
    app = create_app(settings=settings, executor=executor or StubExecutor())
    return TestClient(app)


def _auth() -> dict[str, str]:
    return {"Authorization": f"Bearer {SECRET}"}


def _job(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "kind": "exec",
        "tenant_id": str(uuid4()),
        "workspace_id": str(uuid4()),
        "call_id": str(uuid4()),
        "image": "qzdap/sandbox-python:latest",
        "command": ["python", "/work/main.py"],
        "files": {"main.py": "print('ok')"},
        "timeout_ms": 5000,
        "limits": {"memory_mb": 256, "network": "none"},
    }
    body.update(overrides)
    return body


def test_healthz() -> None:
    client = _app()
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["runtime"] == "stub"


def test_rejects_missing_bearer() -> None:
    client = _app()
    response = client.post("/internal/jobs", json=_job())
    assert response.status_code == 401


def test_image_whitelist() -> None:
    client = _app()
    response = client.post(
        "/internal/jobs",
        json=_job(image="evil/image:latest"),
        headers=_auth(),
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "SANDBOX_IMAGE_DENIED"


def test_exec_job_succeeds() -> None:
    client = _app()
    response = client.post("/internal/jobs", json=_job(), headers=_auth())
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "succeeded"
    assert body["runtime"] == "stub"
    job_id = body["id"]
    fetched = client.get(f"/internal/jobs/{job_id}", headers=_auth())
    assert fetched.status_code == 200
    assert fetched.json()["id"] == job_id


def test_exec_forces_none_network() -> None:
    executor = StubExecutor()
    client = _app(executor)
    response = client.post(
        "/internal/jobs",
        json=_job(limits={"memory_mb": 128, "network": "bridge"}),
        headers=_auth(),
    )
    assert response.status_code == 200
    assert executor.jobs[0].limits.network == "none"


def test_timeout_status() -> None:
    executor = StubExecutor()
    executor.force_status = "timeout"
    client = _app(executor)
    response = client.post("/internal/jobs", json=_job(), headers=_auth())
    assert response.json()["status"] == "timeout"
    assert response.json()["error_code"] == "SANDBOX_TIMEOUT"


def test_clip_and_safe_path() -> None:
    assert "truncated" in clip_output("x" * 10, limit=4)
    with pytest.raises(ValueError):
        safe_relpath("../etc/passwd")


def test_production_refuses_stub() -> None:
    settings = Settings(sandbox_executor="stub", env="production", sandbox_runtime_secret="prod-secret")
    with pytest.raises(RuntimeError, match="stub"):
        create_app(settings=settings)
