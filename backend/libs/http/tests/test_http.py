"""Tests for libs/qzdap_http (mostly smoke)."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from qzdap_http.cors import build_cors_config
from qzdap_http.health import health_router, liveness_router


def test_healthz_returns_ok() -> None:
    app = FastAPI()
    app.include_router(health_router)
    client = TestClient(app)
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_livez_returns_alive() -> None:
    app = FastAPI()
    app.include_router(liveness_router)
    client = TestClient(app)
    r = client.get("/livez")
    assert r.status_code == 200
    assert r.json()["status"] == "alive"


def test_cors_config_parses_env() -> None:
    cfg = build_cors_config(
        {
            "QZDAP_CORS_ALLOW_ORIGINS": "http://a,http://b",
            "QZDAP_CORS_ALLOW_CREDENTIALS": "false",
        }
    )
    assert cfg.allow_origins == ("http://a", "http://b")
    assert cfg.allow_credentials is False
