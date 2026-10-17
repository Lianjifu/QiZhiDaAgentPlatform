"""Phase 16: preview-chain endpoint 集成测试.

验证 admin 配 route 后, 「预览实际会试哪些 model」按钮:
  - success: 返回 {strategy, chain: [{id, name, isPrimary, ...}]}
  - primary 排第一
  - 不存在的 route → 404 / chain=[]
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
async def route_setup() -> Any:
    """Create 1 fresh tenant/workspace + provider + model + route."""
    pg = await asyncpg.connect(_pg_dsn())
    t = uuid.uuid4()
    w = uuid.uuid4()
    user = uuid.uuid4()
    provider_id = uuid.uuid4()
    model_id = uuid.uuid4()
    route_id = uuid.uuid4()
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
        await pg.execute(
            "INSERT INTO admin_models (id, tenant_id, workspace_id, provider_id, name, upstream_model, status, tier, context_window) "
            "VALUES ($1, $2, $3, $4, 'test-model', 'deepseek-chat', 'active', 'balanced', 32000) "
            "ON CONFLICT (id) DO NOTHING",
            model_id, t, w, provider_id,
        )
        await pg.execute(
            "INSERT INTO admin_model_routes (id, tenant_id, workspace_id, name, task, strategy, priority, primary_model_id, fallback_model_ids, enabled, description) "
            "VALUES ($1, $2, $3, 'test-route', 'generation', 'fallback', 0, $4, '[]'::jsonb, true, '') "
            "ON CONFLICT (id) DO NOTHING",
            route_id, t, w, model_id,
        )
        yield {
            "tenant_id": t,
            "workspace_id": w,
            "user_id": user,
            "provider_id": provider_id,
            "model_id": model_id,
            "route_id": route_id,
        }
    finally:
        try:
            await pg.execute(
                "DELETE FROM admin_model_routes WHERE tenant_id = $1", t
            )
            await pg.execute("DELETE FROM admin_models WHERE tenant_id = $1", t)
            await pg.execute(
                "DELETE FROM admin_model_providers WHERE tenant_id = $1", t
            )
            await pg.execute("DELETE FROM users WHERE id = $1", user)
            await pg.execute("DELETE FROM workspaces WHERE id = $1", w)
            await pg.execute("DELETE FROM tenants WHERE id = $1", t)
        finally:
            await pg.close()


@pytest.mark.asyncio
async def test_preview_chain_returns_primary_first(route_setup: Any) -> None:
    """preview_chain: primary 排第一 + 元信息齐全."""
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
        result = await svc.preview_chain(
            tenant_id=route_setup["tenant_id"],
            workspace_id=route_setup["workspace_id"],
            route_id=route_setup["route_id"],
        )
    assert result["routeId"] == str(route_setup["route_id"])
    assert result["routeName"] == "test-route"
    assert result["strategy"] == "fallback"
    assert result["primaryModelId"] == str(route_setup["model_id"])
    assert isinstance(result["chain"], list)
    assert len(result["chain"]) == 1, f"chain 应该是 [primary], got {result['chain']}"
    first = result["chain"][0]
    assert first["id"] == str(route_setup["model_id"])
    assert first["isPrimary"] is True
    assert first["name"] == "test-model"
    assert first["tier"] == "balanced"


@pytest.mark.asyncio
async def test_preview_chain_missing_route_returns_error(route_setup: Any) -> None:
    """preview_chain: 不存在的 route → chain=[] + error 字段."""
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
        result = await svc.preview_chain(
            tenant_id=route_setup["tenant_id"],
            workspace_id=route_setup["workspace_id"],
            route_id=uuid.uuid4(),  # 不存在
        )
    assert result["chain"] == []
    assert "error" in result, f"expected error, got {result}"
