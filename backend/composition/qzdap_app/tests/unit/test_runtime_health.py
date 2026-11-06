"""Tests for Container._collect_runtime_health —— 运行时健康报告.

⚠️ **不再是启动闸门** ✓ —— 以前这里是「生产环境拒绝启动」✓（默认密钥 /
默认后端 → 抛 RuntimeError ✓），但仓库现在**只有一个开发环境** ✓ → 那道
闸门永远不触发 ✓。检查项保留 ✓，改成**如实报告** ✓（``degraded`` =
降级了的能力 ✓，``issues`` = 缺必需项 ✓）—— **启动不崩** ✓。

The settings dataclass is permissive by design — the real defaults flow
through pydantic-settings + the ``QZDAP_*_REF`` indirection. Tests here
construct ``Settings`` instances directly with the exact values we want to
probe.
"""

from __future__ import annotations

from typing import cast

import pytest
from pydantic import PydanticUserError

from qzdap.composition.container import Container
from qzdap.composition.settings import Settings


def _settings(**overrides: object) -> Settings:
    """Build a Settings instance with any field overrides. Pydantic-settings
    reads env vars at construction time, so we set them via os.environ then
    construct.
    """
    import os

    saved: dict[str, str | None] = {}
    keys = (
        "QZDAP_ENV",
        "QZDAP_JWT_SECRET",
        "QZDAP_SANDBOX_RUNTIME_SECRET",
        "QZDAP_DEV_ADMIN_PASSWORD",
        "QZDAP_MODEL_MASTER_KEY",
        "QZDAP_SKILL_SIGNING_MODE",
        "QZDAP_KNOWLEDGE_SIGNING_MODE",
        "QZDAP_PLAN_SIGNING_MODE",
        "QZDAP_EMBEDDING_PROVIDER",
        "QZDAP_VAULT_MODE",
        "QZDAP_EVENT_BUS",
    )
    for k in keys:
        saved[k] = os.environ.get(k)
        os.environ.pop(k, None)

    base: dict[str, object] = {
        "env": "development",
        "jwt_secret": "dev-jwt-secret",
        "sandbox_runtime_secret": "dev-sandbox-runtime-secret",
        "sandbox_runtime_url": "http://127.0.0.1:9158",
        "dev_admin_password": "dev-admin-password",
        "model_master_key": "dev-model-master-key",
        # backend selections (fully configured)
        "embedding_provider": "openai",
        "vault_mode": "csi",
        "event_bus": "redis-stream",
    }
    base.update(overrides)
    try:
        return Settings(**base)  # type: ignore[arg-type]
    except PydanticUserError:
        # older pydantic versions: try without **kwargs
        for k, v in base.items():
            os.environ[f"QZDAP_{k.upper()}"] = str(v)
        return Settings(env="development")  # type: ignore[call-arg]
    finally:
        for k, v in saved.items():
            if v is not None:
                os.environ[k] = v


# ── happy path ────────────────────────────────────────────────────────────


def test_fully_configured_settings_report_nothing() -> None:
    container = Container(_settings())
    assert container.runtime_health == {"degraded": [], "issues": []}


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["complete", "error", "close", "cancel"])
async def test_saved_model_stream_facade_session_lifecycle(monkeypatch, outcome: str) -> None:
    import asyncio
    from contextlib import asynccontextmanager
    from types import SimpleNamespace
    from uuid import uuid4

    from qzdap.modules.model.adapter.llm import client_factory
    from qzdap.modules.model.adapter.persistence import repositories
    from qzdap.modules.model.application import services
    from qzdap_kernel.ids import TenantId, WorkspaceId
    from qzdap_llm.client import ChatRequest, LLMChunk
    from qzdap_vault.actor import ActorContext

    events: list[str] = []
    waiting = asyncio.Event()
    actor = ActorContext(
        tenant_id=TenantId(uuid4()),
        workspace_id=WorkspaceId(uuid4()),
        principal_id=uuid4(),
    )
    saved_id = uuid4()
    req = ChatRequest(model="saved", messages=[])

    class DBSession:
        async def commit(self):
            events.append("commit")

        async def rollback(self):
            events.append("rollback")

    class Sessions:
        @asynccontextmanager
        async def session(self):
            events.append("open")
            try:
                yield DBSession()
            finally:
                events.append("exit")

    class Service:
        def __init__(self, *args, **kwargs):
            pass

        async def stream(self, **kwargs):
            assert kwargs == {"actor": actor, "model_id": saved_id, "req": req}
            try:
                yield LLMChunk(model="upstream", delta="first")
                if outcome == "error":
                    raise ValueError("provider failed")
                if outcome == "cancel":
                    waiting.set()
                    await asyncio.Event().wait()
                yield LLMChunk(model="upstream", delta="", finish_reason="stop")
            finally:
                events.append("provider_closed")

    monkeypatch.setattr(services, "ModelService", Service)
    monkeypatch.setattr(client_factory, "build_default_client_factory", lambda **kwargs: object())
    for name in (
        "SqlModelRepository",
        "SqlProviderRepository",
        "SqlRouteRepository",
        "SqlHealthRepository",
    ):
        monkeypatch.setattr(repositories, name, lambda session: object())
    host = SimpleNamespace(
        settings=SimpleNamespace(model_invocation_timeout_seconds=1),
        model_credential_cipher=lambda: object(),
        session_factory=lambda: Sessions(),
    )
    facade = Container.model_service(cast("Container", host))
    stream = facade.stream(actor=actor, model_id=saved_id, req=req)
    assert (await anext(stream)).delta == "first"
    assert events == ["open"]
    if outcome == "complete":
        assert len([chunk async for chunk in stream]) == 1
    elif outcome == "error":
        with pytest.raises(ValueError, match="provider failed"):
            await anext(stream)
    elif outcome == "close":
        await stream.aclose()
    else:
        task = asyncio.create_task(anext(stream))
        await waiting.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert events == [
        "open",
        "provider_closed",
        "commit" if outcome == "complete" else "rollback",
        "exit",
    ]


# ── 缺必需项 → issues（不抛异常 ✓）────────────────────────────────────────


def test_empty_model_master_key_is_reported_as_issue() -> None:
    container = Container(_settings(model_master_key=""))
    assert any("QZDAP_MODEL_MASTER_KEY" in item for item in container.runtime_health["issues"])


def test_empty_sandbox_runtime_url_is_reported_as_issue() -> None:
    container = Container(_settings(sandbox_runtime_url=""))
    assert any("QZDAP_SANDBOX_RUNTIME_URL" in item for item in container.runtime_health["issues"])


# ── 降级的后端 → degraded（不抛异常 ✓）────────────────────────────────────


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("embedding_provider", "noop", "QZDAP_EMBEDDING_PROVIDER"),
        ("vault_mode", "env", "QZDAP_VAULT_MODE"),
        ("vault_mode", "noop", "QZDAP_VAULT_MODE"),
        ("event_bus", "inprocess", "QZDAP_EVENT_BUS"),
    ],
)
def test_degraded_backend_is_reported(field: str, value: str, expected: str) -> None:
    container = Container(_settings(**{field: value}))
    assert any(item.startswith(expected) for item in container.runtime_health["degraded"])


def test_multiple_degradations_are_reported_together() -> None:
    container = Container(
        _settings(
            embedding_provider="noop",
            event_bus="inprocess",
        )
    )
    degraded = container.runtime_health["degraded"]
    assert any("QZDAP_EMBEDDING_PROVIDER" in item for item in degraded)
    assert any("QZDAP_EVENT_BUS" in item for item in degraded)


# ── 任何 env 都不再抛异常 ✓ ───────────────────────────────────────────────


@pytest.mark.parametrize("env_value", ["development", "test", "ci"])
def test_no_env_ever_raises(env_value: str) -> None:
    """健康检查**永远不拦启动** ✓ —— 降级项只报告 ✓。"""
    settings = _settings(env=env_value)
    container = Container(settings)
    assert isinstance(container.runtime_health["degraded"], list)
    assert isinstance(container.runtime_health["issues"], list)
