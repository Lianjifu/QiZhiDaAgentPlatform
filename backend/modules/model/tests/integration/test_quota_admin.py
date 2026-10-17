"""Phase 17: quota admin endpoints 集成测试.

验证 admin 「配额管理」UI 数据源:
  - list_quotas / upsert_quota / delete_quota
  - list_usage 聚合 model_quota_usage
  - upsert 是 idempotent (按 (model_id, period) 更新, 不是新增)
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
async def quota_setup() -> Any:
    """Create 1 fresh tenant/workspace + provider + model (无 quota)."""
    pg = await asyncpg.connect(_pg_dsn())
    t = uuid.uuid4()
    w = uuid.uuid4()
    user = uuid.uuid4()
    provider_id = uuid.uuid4()
    model_id = uuid.uuid4()
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
        yield {
            "tenant_id": t,
            "workspace_id": w,
            "user_id": user,
            "provider_id": provider_id,
            "model_id": model_id,
        }
    finally:
        try:
            await pg.execute(
                "DELETE FROM model_quota_usage WHERE tenant_id = $1", t
            )
            await pg.execute(
                "DELETE FROM model_quotas WHERE tenant_id = $1", t
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
async def test_upsert_quota_creates_then_updates(quota_setup: Any) -> None:
    """upsert: 首次创建, 再次同 (model, period) 更新."""
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
        # 1. 首次创建
        created = await svc.upsert_quota(
            tenant_id=quota_setup["tenant_id"],
            workspace_id=quota_setup["workspace_id"],
            body={
                "modelId": str(quota_setup["model_id"]),
                "period": "minute",
                "maxTokensIn": 1000,
                "maxTokensOut": 500,
                "maxRequests": 10,
                "description": "first",
            },
        )
        assert created["maxTokensIn"] == 1000
        assert created["maxRequests"] == 10
        quota_id = created["id"]
        # 2. 再次 upsert (同 model + period) → 应该是 update 不是 insert
        updated = await svc.upsert_quota(
            tenant_id=quota_setup["tenant_id"],
            workspace_id=quota_setup["workspace_id"],
            body={
                "modelId": str(quota_setup["model_id"]),
                "period": "minute",
                "maxTokensIn": 2000,
                "maxTokensOut": 1000,
                "maxRequests": 20,
                "description": "second",
            },
        )
        assert updated["id"] == quota_id, "upsert 不应新增行"
        assert updated["maxTokensIn"] == 2000
        assert updated["maxRequests"] == 20
        # 3. list 应该是 1 条
        all_q = await svc.list_quotas(
            tenant_id=quota_setup["tenant_id"],
            workspace_id=quota_setup["workspace_id"],
        )
        assert len(all_q) == 1, f"expected 1, got {len(all_q)}"


@pytest.mark.asyncio
async def test_upsert_quota_invalid_period_raises(quota_setup: Any) -> None:
    """period 不在白名单 → 422 (admin 应该看到清晰的错误)."""
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
        with pytest.raises(ValueError, match="period 必须是"):
            await svc.upsert_quota(
                tenant_id=quota_setup["tenant_id"],
                workspace_id=quota_setup["workspace_id"],
                body={
                    "modelId": str(quota_setup["model_id"]),
                    "period": "year",  # 不在白名单
                    "maxRequests": 10,
                },
            )


@pytest.mark.asyncio
async def test_delete_quota_removes_row(quota_setup: Any) -> None:
    """delete 后 list 应该少一条."""
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
        created = await svc.upsert_quota(
            tenant_id=quota_setup["tenant_id"],
            workspace_id=quota_setup["workspace_id"],
            body={
                "modelId": str(quota_setup["model_id"]),
                "period": "day",
                "maxRequests": 100,
            },
        )
        before = await svc.list_quotas(
            tenant_id=quota_setup["tenant_id"],
            workspace_id=quota_setup["workspace_id"],
        )
        assert len(before) == 1
        await svc.delete_quota(quota_id=uuid.UUID(created["id"]))
        after = await svc.list_quotas(
            tenant_id=quota_setup["tenant_id"],
            workspace_id=quota_setup["workspace_id"],
        )
        assert len(after) == 0
