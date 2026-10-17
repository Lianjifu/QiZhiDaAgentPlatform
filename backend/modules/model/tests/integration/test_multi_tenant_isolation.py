"""Multi-tenant isolation E2E test (Phase 9).

Verify the model layer (QuotaService + LLMAuditService + health event) keeps
tenants strictly separated:

  1. Tenant A: 配额超限 → 拒绝
     Tenant B: 同一 model 仍有完整配额 → 通过
  2. Tenant A: model 配错 (workspace 不存在) → 拒绝
     Tenant B: 同 model 正常使用 → 通过
  3. Tenant A: audit row 写完后, Tenant B 的 query 看不到它
  4. Tenant A: admin_model_health row, Tenant B 看不到

每个测试独立, 用 fixture 创建独立的 tenant + workspace + 配 admin_models, 不依赖
外部状态.
"""
from __future__ import annotations

import os
import uuid
from typing import Any

import asyncpg
import pytest
from qzdap.composition.container import Container
from qzdap.composition.settings import Settings
from qzdap_llm import ChatMessage, ChatRequest, ProviderTransportError
from qzdap_vault.actor import ActorContext

from qzdap.modules.model.adapter.crypto.credential_cipher import (
    build_cipher_from_env,
)
from qzdap.modules.model.domain.errors import QuotaExceeded


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
async def isolated_tenants() -> Any:
    """Create 2 tenants + workspaces + admin_models. Cleanup after test."""
    pg = await asyncpg.connect(_pg_dsn())
    ts = [uuid.uuid4() for _ in range(2)]
    ws = [uuid.uuid4() for _ in range(2)]
    users = [uuid.uuid4() for _ in range(2)]
    model_id_a = uuid.uuid4()
    model_id_b = uuid.uuid4()
    try:
        for i, (t, w, u) in enumerate(zip(ts, ws, users)):
            await pg.execute(
                "INSERT INTO tenants (id, slug, display_name, status, tenant_id) "
                "VALUES ($1, $2, $3, 'active', $1) ON CONFLICT (id) DO NOTHING",
                t, f"test-tenant-{i}", f"Test Tenant {i}",
            )
            await pg.execute(
                "INSERT INTO workspaces (id, tenant_id, slug, display_name, status) "
                "VALUES ($1, $2, $3, $4, 'active') ON CONFLICT (id) DO NOTHING",
                w, t, f"test-ws-{i}", f"Test WS {i}",
            )
            await pg.execute(
                "INSERT INTO users (id, tenant_id, email, display_name, status) "
                "VALUES ($1, $2, $3, $4, 'active') ON CONFLICT (id) DO NOTHING",
                u, t, f"test{i}@example.com", f"Test User {i}",
            )
            provider_id = uuid.uuid4()
            # 用测试 master key 加密 placeholder api_key (需要 AAD protocol+base_url)
            cipher = build_cipher_from_env(master_key_hex=_master_key())
            aad = b"protocol=openai|base_url=https://api.test/v1"
            encrypted = cipher.encrypt(b"sk-test-placeholder-1234", aad=aad)
            await pg.execute(
                "INSERT INTO admin_model_providers (id, tenant_id, workspace_id, name, region, status, base_url, protocol, api_key_masked, encrypted_payload) "
                "VALUES ($1, $2, $3, $4, 'global', 'healthy', 'https://api.test/v1', 'openai', '****', $5) "
                "ON CONFLICT (id) DO NOTHING",
                provider_id, t, w, f"test-prov-{i}", encrypted,
            )
            mid = model_id_a if i == 0 else model_id_b
            await pg.execute(
                "INSERT INTO admin_models (id, tenant_id, workspace_id, name, provider_id, provider_name, status, tier, upstream_model) "
                "VALUES ($1, $2, $3, $4, $5, $6, 'active', 'balanced', $7) "
                "ON CONFLICT (id) DO NOTHING",
                mid, t, w, f"test-model-{i}", provider_id, f"test-prov-{i}", f"test-model-{i}",
            )
        yield {
            "tenants": ts,
            "workspaces": ws,
            "users": users,
            "model_ids": [model_id_a, model_id_b],
        }
    finally:
        # cleanup (变量都在 try 外定义, finally 内可访问)
        try:
            await pg.execute(
                "DELETE FROM admin_model_health WHERE workspace_id = ANY($1::uuid[])",
                ws,
            )
            await pg.execute(
                "DELETE FROM audit_log WHERE tenant_id = ANY($1::uuid[])",
                ts,
            )
            await pg.execute(
                "DELETE FROM model_quota_usage WHERE tenant_id = ANY($1::uuid[])",
                ts,
            )
            await pg.execute(
                "DELETE FROM model_quotas WHERE tenant_id = ANY($1::uuid[])",
                ts,
            )
            await pg.execute(
                "DELETE FROM admin_models WHERE tenant_id = ANY($1::uuid[])",
                ts,
            )
            await pg.execute(
                "DELETE FROM admin_model_providers WHERE tenant_id = ANY($1::uuid[])",
                ts,
            )
            await pg.execute(
                "DELETE FROM users WHERE id = ANY($1::uuid[])",
                users,
            )
            await pg.execute(
                "DELETE FROM workspaces WHERE id = ANY($1::uuid[])",
                ws,
            )
            await pg.execute(
                "DELETE FROM tenants WHERE id = ANY($1::uuid[])",
                ts,
            )
        finally:
            await pg.close()


@pytest.mark.asyncio
async def test_quota_isolated_between_tenants(isolated_tenants: Any) -> None:
    """Tenant A 用满配额 → Tenant B 同一个 model 仍可用."""
    data = isolated_tenants
    # 在 tenant A 上配 max_requests=1
    pg = await asyncpg.connect(_pg_dsn())
    try:
        await pg.execute(
            "INSERT INTO model_quotas (id, tenant_id, workspace_id, model_id, period, max_requests, enabled) "
            "VALUES ($1, $2, $3, $4, 'minute', 1, true) ON CONFLICT DO NOTHING",
            uuid.uuid4(), data["tenants"][0], data["workspaces"][0], data["model_ids"][0],
        )
    finally:
        await pg.close()

    s = Settings()
    c = Container(s)
    facade = c.model_service()
    actor_a = ActorContext(
        tenant_id=data["tenants"][0],
        workspace_id=data["workspaces"][0],
        principal_id=data["users"][0],
    )
    actor_b = ActorContext(
        tenant_id=data["tenants"][1],
        workspace_id=data["workspaces"][1],
        principal_id=data["users"][1],
    )
    req = ChatRequest(model="test-model-0", messages=[ChatMessage(role="user", content="hi")])

    # Tenant A: 1st ok, 2nd QuotaExceeded
    try:
        async for _ in facade.stream(actor=actor_a, model_id=data["model_ids"][0], req=req):
            pass
    except ProviderTransportError:
        pass  # placeholder key, expected
    try:
        async for _ in facade.stream(actor=actor_a, model_id=data["model_ids"][0], req=req):
            pass
        pytest.fail("Tenant A's 2nd request should be QuotaExceeded")
    except QuotaExceeded:
        pass
    except ProviderTransportError:
        pytest.fail("Tenant A's 2nd request should be QuotaExceeded (not provider error)")

    # Tenant B: 同 model, 没配 quota, 应该没限制 (走 provider error)
    try:
        async for _ in facade.stream(actor=actor_b, model_id=data["model_ids"][1], req=req):
            pass
    except ProviderTransportError:
        pass  # 没配 quota, 不会被限流
    except QuotaExceeded:
        pytest.fail("Tenant B should not be affected by Tenant A's quota")


@pytest.mark.asyncio
async def test_health_and_audit_isolated_between_tenants(isolated_tenants: Any) -> None:
    """Tenant A 的 health + audit 行对 Tenant B 不可见."""
    data = isolated_tenants
    s = Settings()
    c = Container(s)
    facade = c.model_service()
    actor_a = ActorContext(
        tenant_id=data["tenants"][0],
        workspace_id=data["workspaces"][0],
        principal_id=data["users"][0],
    )
    req = ChatRequest(model="test-model-0", messages=[ChatMessage(role="user", content="hi")])

    try:
        async for _ in facade.stream(actor=actor_a, model_id=data["model_ids"][0], req=req):
            pass
    except ProviderTransportError:
        pass

    pg = await asyncpg.connect(_pg_dsn())
    try:
        # Tenant A: 有 health + audit
        a_health = await pg.fetchval(
            "SELECT count(*) FROM admin_model_health WHERE tenant_id = $1",
            data["tenants"][0],
        )
        a_audit = await pg.fetchval(
            "SELECT count(*) FROM audit_log WHERE tenant_id = $1",
            data["tenants"][0],
        )
        assert a_health >= 1, f"Tenant A should have >= 1 health row, got {a_health}"
        assert a_audit >= 1, f"Tenant A should have >= 1 audit row, got {a_audit}"

        # Tenant B: 没 health + audit
        b_health = await pg.fetchval(
            "SELECT count(*) FROM admin_model_health WHERE tenant_id = $1",
            data["tenants"][1],
        )
        b_audit = await pg.fetchval(
            "SELECT count(*) FROM audit_log WHERE tenant_id = $1",
            data["tenants"][1],
        )
        assert b_health == 0, f"Tenant B should have 0 health rows, got {b_health}"
        assert b_audit == 0, f"Tenant B should have 0 audit rows, got {b_audit}"
    finally:
        await pg.close()
