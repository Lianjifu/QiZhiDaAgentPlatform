"""Tests for Container._validate_production_secrets — boot-time prod gate.

The gate fires only when ``settings.env == "production"``. In every other
env (development / staging / test / ci) it must be a no-op so dev shells
can run with the development defaults.

The settings dataclass is permissive by design — the real prod defaults
flow through pydantic-settings + the ``QZDAP_*_REF`` indirection. Tests
here construct ``Settings`` instances directly with the exact values we
want to probe.
"""

from __future__ import annotations

import pytest
from pydantic import PydanticUserError

from qzdap.composition.container import Container
from qzdap.composition.settings import Settings


def _prod_settings(**overrides: object) -> Settings:
    """Build a Settings instance with ``env='production'`` and any field
    overrides. Pydantic-settings reads env vars at construction time, so
    we set them via os.environ then construct.
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
        "env": "production",
        # sentinel-free secret values
        "jwt_secret": "prod-jwt-secret-please",
        "sandbox_runtime_secret": "prod-sandbox-runtime-secret",
        "sandbox_runtime_url": "http://sandbox-runtime:8093",
        "dev_admin_password": "real-admin-password",
        "model_master_key": "prod-model-master-key",
        # backend selections (prod-safe)
        "skill_signing_mode": "local",
        "knowledge_signing_mode": "local",
        "plan_signing_mode": "local",
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
        return Settings(env="production")  # type: ignore[call-arg]
    finally:
        for k, v in saved.items():
            if v is not None:
                os.environ[k] = v


# ── happy path ────────────────────────────────────────────────────────────


def test_prod_settings_with_safe_values_passes() -> None:
    settings = _prod_settings()
    # should not raise
    Container(settings)


# ── raw-secret sentinel detection ────────────────────────────────────────


def test_prod_env_with_dev_jwt_secret_raises() -> None:
    settings = _prod_settings(jwt_secret="dev-jwt-secret")
    with pytest.raises(RuntimeError, match="QZDAP_JWT_SECRET"):
        Container(settings)


def test_prod_env_with_dev_sandbox_runtime_secret_raises() -> None:
    settings = _prod_settings(sandbox_runtime_secret="dev_placeholder")
    with pytest.raises(RuntimeError, match="QZDAP_SANDBOX_RUNTIME_SECRET"):
        Container(settings)


def test_prod_env_with_empty_admin_password_raises() -> None:
    settings = _prod_settings(dev_admin_password="")
    with pytest.raises(RuntimeError, match="QZDAP_DEV_ADMIN_PASSWORD"):
        Container(settings)


def test_prod_env_with_dev_model_master_key_raises() -> None:
    settings = _prod_settings(model_master_key="dev-please-rotate")
    with pytest.raises(RuntimeError, match="QZDAP_MODEL_MASTER_KEY"):
        Container(settings)


# ── dev-default backend refusal ──────────────────────────────────────────


def test_prod_env_with_disabled_skill_signing_raises() -> None:
    settings = _prod_settings(skill_signing_mode="disabled")
    with pytest.raises(RuntimeError, match="QZDAP_SKILL_SIGNING_MODE"):
        Container(settings)


def test_prod_env_with_disabled_knowledge_signing_raises() -> None:
    settings = _prod_settings(knowledge_signing_mode="disabled")
    with pytest.raises(RuntimeError, match="QZDAP_KNOWLEDGE_SIGNING_MODE"):
        Container(settings)


def test_prod_env_with_disabled_plan_signing_raises() -> None:
    settings = _prod_settings(plan_signing_mode="disabled")
    with pytest.raises(RuntimeError, match="QZDAP_PLAN_SIGNING_MODE"):
        Container(settings)


def test_prod_env_with_noop_embedding_raises() -> None:
    settings = _prod_settings(embedding_provider="noop")
    with pytest.raises(RuntimeError, match="QZDAP_EMBEDDING_PROVIDER"):
        Container(settings)


def test_prod_env_with_env_vault_mode_raises() -> None:
    settings = _prod_settings(vault_mode="env")
    with pytest.raises(RuntimeError, match="QZDAP_VAULT_MODE"):
        Container(settings)


def test_prod_env_with_noop_vault_mode_raises() -> None:
    settings = _prod_settings(vault_mode="noop")
    with pytest.raises(RuntimeError, match="QZDAP_VAULT_MODE"):
        Container(settings)


def test_prod_env_with_inprocess_event_bus_raises() -> None:
    settings = _prod_settings(event_bus="inprocess")
    with pytest.raises(RuntimeError, match="QZDAP_EVENT_BUS"):
        Container(settings)


# ── multiple offenders are reported in one error ─────────────────────────


def test_prod_env_with_multiple_offenders_raises_once() -> None:
    settings = _prod_settings(
        skill_signing_mode="disabled",
        embedding_provider="noop",
        event_bus="inprocess",
    )
    with pytest.raises(RuntimeError) as excinfo:
        Container(settings)
    msg = str(excinfo.value)
    assert "QZDAP_SKILL_SIGNING_MODE" in msg
    assert "QZDAP_EMBEDDING_PROVIDER" in msg
    assert "QZDAP_EVENT_BUS" in msg


# ── env gate: dev/staging/test must NOT trigger ──────────────────────────


@pytest.mark.parametrize("env_value", ["development", "test", "ci", "staging"])
def test_non_prod_env_never_triggers_gate(env_value: str) -> None:
    """Every non-production env must pass through with all dev defaults."""
    settings = _prod_settings(env=env_value)
    # dev-default backends are allowed outside production
    settings = _prod_settings(  # type: ignore[assignment]
        env=env_value,  # type: ignore[arg-type]
        skill_signing_mode="disabled",
        embedding_provider="noop",
        vault_mode="env",
        event_bus="inprocess",
    )
    # should not raise
    Container(settings)