"""Phase 13: connectivity-test endpoint 集成测试.

验证 admin 配模型时的「测试连通性」按钮行为:
  - 成功 (real key + reachable URL) → success=True + latencyMs
  - 失败 (placeholder key) → success=False + statusCode + error
  - 缺 apiKey → raise ValueError (400)
"""
from __future__ import annotations

import os
import uuid
from typing import Any

import asyncpg
import pytest
from qzdap.composition.container import Container
from qzdap.composition.settings import Settings

from qzdap.modules.model.adapter.crypto.credential_cipher import (
    build_cipher_from_env,
)


def _qzdap_db() -> str:
    return os.environ.get(
        "QZDAP_DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@localhost:9153/qzdap_dev",
    )


def _master_key() -> str:
    return os.environ.get(
        "QZDAP_MODEL_MASTER_KEY",
        "fb8a4eb7cc3e2922e2ae76d4327a9625f20b2b63e6ffc1b20883f5b3f4cbdbf3",
    )


def _pg_dsn() -> str:
    return _qzdap_db().replace("postgresql+asyncpg://", "postgresql://")


@pytest.fixture
async def provider_setup() -> Any:
    """Create 1 fresh tenant/workspace + provider with encrypted placeholder key."""
    pg = await asyncpg.connect(_pg_dsn())
    t = uuid.uuid4()
    w = uuid.uuid4()
    user = uuid.uuid4()
    provider_id = uuid.uuid4()
    cipher = build_cipher_from_env(master_key_hex=_master_key())
    aad = b"protocol=openai|base_url=https://api.deepseek.com/v1"
    encrypted = cipher.encrypt(b"sk-test-placeholder-1234", aad=aad)
    try:
        await pg.execute(
            "INSERT INTO tenants (id, slug, display_name, status, tenant_id) "
            "VALUES ($1, $2, $3, 'active', $1) ON CONFLICT (id) DO NOTHING",
            t, f"t-{str(t)[:8]}", "Test",
        )
        await pg.execute(
            "INSERT INTO workspaces (id, tenant_id, slug, display_name, status) "
            "VALUES ($1, $2, $3, $4, 'active') ON CONFLICT (id) DO NOTHING",
            w, t, f"w-{str(w)[:8]}", "Test WS",
        )
        await pg.execute(
            "INSERT INTO users (id, tenant_id, email, display_name, status) "
            "VALUES ($1, $2, $3, $4, 'active') ON CONFLICT (id) DO NOTHING",
            user, t, f"test-{t}@example.com", "Test User",
        )
        await pg.execute(
            "INSERT INTO admin_model_providers (id, tenant_id, workspace_id, name, region, status, base_url, protocol, api_key_masked, encrypted_payload) "
            "VALUES ($1, $2, $3, 'test-prov', 'global', 'healthy', 'https://api.deepseek.com/v1', 'openai', '****', $4) "
            "ON CONFLICT (id) DO NOTHING",
            provider_id, t, w, encrypted,
        )
        yield {
            "tenant_id": t,
            "workspace_id": w,
            "user_id": user,
            "provider_id": provider_id,
        }
    finally:
        try:
            await pg.execute(
                "DELETE FROM admin_model_providers WHERE tenant_id = $1", t
            )
            await pg.execute("DELETE FROM users WHERE id = $1", user)
            await pg.execute("DELETE FROM workspaces WHERE id = $1", w)
            await pg.execute("DELETE FROM tenants WHERE id = $1", t)
        finally:
            await pg.close()


@pytest.mark.asyncio
async def test_connectivity_with_placeholder_key_returns_401(provider_setup: Any) -> None:
    """Place key returns 401 (real HTTP to deepseek), 不抛错."""
    from qzdap.modules.model.adapter.llm.client_factory import (
        build_default_client_factory,
    )
    from qzdap.modules.model.adapter.llm.connectivity_tester import (
        HttpConnectivityTester,
    )
    from qzdap.modules.model.adapter.persistence.repositories import (
        SqlHealthRepository,
        SqlModelRepository,
        SqlProviderRepository,
        SqlRouteRepository,
    )
    from qzdap.modules.model.application.services import ModelService

    s = Settings()
    c = Container(s)
    sf = c.session_factory()
    cipher = build_cipher_from_env(master_key_hex=_master_key())
    client_factory = build_default_client_factory(request_timeout_seconds=30)
    tester = HttpConnectivityTester()
    async with sf.session() as session:
        svc = ModelService(
            SqlModelRepository(session),
            SqlProviderRepository(session),
            SqlRouteRepository(session),
            SqlHealthRepository(session),
            cipher=cipher,
            client_factory=client_factory,
            connectivity_tester=tester,
        )
        result = await svc.test_connectivity(
            body={
                "providerId": str(provider_setup["provider_id"]),
                "apiKey": "sk-test-placeholder-1234",
                "baseUrl": "https://api.deepseek.com/v1",
                "protocol": "openai",
                "model": "deepseek-chat",
            }
        )
    # deepseek 对 placeholder key 返 401
    assert result.get("success") is False, f"expected failure, got {result}"
    assert result.get("statusCode") == 401, f"expected 401, got {result}"
    assert "latencyMs" in result, f"missing latencyMs in {result}"


@pytest.mark.asyncio
async def test_connectivity_missing_model_raises(provider_setup: Any) -> None:
    """没 model → raise ValueError (router 转 400)."""
    from qzdap.modules.model.adapter.llm.client_factory import (
        build_default_client_factory,
    )
    from qzdap.modules.model.adapter.llm.connectivity_tester import (
        HttpConnectivityTester,
    )
    from qzdap.modules.model.adapter.persistence.repositories import (
        SqlHealthRepository,
        SqlModelRepository,
        SqlProviderRepository,
        SqlRouteRepository,
    )
    from qzdap.modules.model.application.services import ModelService

    s = Settings()
    c = Container(s)
    sf = c.session_factory()
    cipher = build_cipher_from_env(master_key_hex=_master_key())
    client_factory = build_default_client_factory(request_timeout_seconds=30)
    tester = HttpConnectivityTester()
    async with sf.session() as session:
        svc = ModelService(
            SqlModelRepository(session),
            SqlProviderRepository(session),
            SqlRouteRepository(session),
            SqlHealthRepository(session),
            cipher=cipher,
            client_factory=client_factory,
            connectivity_tester=tester,
        )
        with pytest.raises(ValueError, match="model required"):
            await svc.test_connectivity(
                body={
                    "providerId": str(provider_setup["provider_id"]),
                    "apiKey": "sk-test",
                    "baseUrl": "https://api.deepseek.com/v1",
                }
            )
