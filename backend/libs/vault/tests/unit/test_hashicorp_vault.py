"""Unit tests for the HashiCorp Vault resolver.

We don't reach out to a real Vault server in CI.  Instead we inject a
fake ``hvac.Client`` shim into the resolver's private slot and verify
the contract: KV v2 lookup, error mapping (InvalidPath / Forbidden /
transport), TTL cache behaviour, and actor-context plumbing.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest

from qzdap_vault import (
    ActorContext,
    HashicorpVaultSecretsResolver,
    InvalidSecretRef,
    SecretAccessDenied,
    SecretNotFound,
    VaultSecretsResolver,
)


def _actor() -> ActorContext:
    return ActorContext(tenant_id=UUID(int=1), workspace_id=UUID(int=2))


class _InvalidPath(Exception):
    pass


class _Forbidden(Exception):
    """Stand-in for hvac's Forbidden.  Test-private class name kept to
    exercise the production-side ``type(exc).__name__`` mapping (which
    matches the bare ``Forbidden`` class name)."""


class _FakeKV2:
    """Mirrors ``hvac.api.secrets_kv.v2.KvV2.read_secret``.

    Lookup key = the path passed to ``read_secret`` (mount is implicit
    via the engine binding, not part of the logical key).
    """

    def __init__(
        self, payloads: dict[str, dict[str, str]], *, fail: str | None = None
    ) -> None:
        self._payloads = payloads
        self._fail = fail
        self.calls = 0

    def read_secret(self, *, path: str, mount_point: str) -> dict[str, Any]:
        self.calls += 1
        if self._fail == "forbidden":
            raise _Forbidden(f"forbidden for {mount_point}/{path}")
        if self._fail == "transport":
            raise RuntimeError("connection reset")
        if self._fail == "invalid":
            raise _InvalidPath(f"no secret at {mount_point}/{path}")
        if path not in self._payloads:
            raise _InvalidPath(f"no secret at {mount_point}/{path}")
        return {"data": {"data": self._payloads[path]}}


class _FakeV2:
    def __init__(self, inner: _FakeKV2) -> None:
        self._inner = inner

    def read_secret(self, *, path: str, mount_point: str) -> dict[str, Any]:
        return self._inner.read_secret(path=path, mount_point=mount_point)


class _FakeKV:
    def __init__(self, v2: _FakeV2) -> None:
        self.v2 = v2


class _FakeSecrets:
    def __init__(self, kv: _FakeKV) -> None:
        self.kv = kv


class _FakeClient:
    def __init__(
        self, payloads: dict[str, dict[str, str]], *, fail: str | None = None
    ) -> None:
        self.kv2 = _FakeKV2(payloads, fail=fail)
        self.secrets = _FakeSecrets(_FakeKV(_FakeV2(self.kv2)))


def _install_fake(resolver: HashicorpVaultSecretsResolver, fake: _FakeClient) -> None:
    resolver._client = fake  # type: ignore[assignment]


# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_hashicorp_resolver_reads_kv_v2(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    r = HashicorpVaultSecretsResolver(
        url="https://vault.test", token="hvs.x", mount_point="secret"
    )
    _install_fake(r, _FakeClient({"api/token": {"value": "v123"}}))

    out = await r.resolve("vault:secret/data/api/token", actor=_actor())
    assert out == {"value": "v123"}


@pytest.mark.asyncio
async def test_hashicorp_resolver_invalid_path_raises_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    r = HashicorpVaultSecretsResolver(url="https://vault.test", token="x")
    _install_fake(r, _FakeClient({}, fail="invalid"))

    with pytest.raises(SecretNotFound):
        await r.resolve("vault:secret/data/missing", actor=_actor())


@pytest.mark.asyncio
async def test_hashicorp_resolver_forbidden_raises_denied(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    r = HashicorpVaultSecretsResolver(url="https://vault.test", token="x")
    _install_fake(r, _FakeClient({}, fail="forbidden"))

    with pytest.raises(SecretAccessDenied):
        await r.resolve("vault:secret/data/locked", actor=_actor())


@pytest.mark.asyncio
async def test_hashicorp_resolver_transport_error_maps_to_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    r = HashicorpVaultSecretsResolver(url="https://vault.test", token="x")
    _install_fake(r, _FakeClient({}, fail="transport"))

    with pytest.raises(SecretNotFound):
        await r.resolve("vault:secret/data/x", actor=_actor())


@pytest.mark.asyncio
async def test_hashicorp_resolver_empty_payload_raises_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    r = HashicorpVaultSecretsResolver(url="https://vault.test", token="x")
    _install_fake(r, _FakeClient({"secret/x": {}}))

    with pytest.raises(SecretNotFound):
        await r.resolve("vault:secret/data/x", actor=_actor())


@pytest.mark.asyncio
async def test_hashicorp_resolver_cache_hits_second_call() -> None:
    r = HashicorpVaultSecretsResolver(
        url="https://vault.test", token="x", cache_ttl_seconds=60.0
    )
    fake = _FakeClient({"api/token": {"value": "v"}})
    _install_fake(r, fake)

    await r.resolve("vault:secret/data/api/token", actor=_actor())
    await r.resolve("vault:secret/data/api/token", actor=_actor())
    await r.resolve("vault:secret/data/api/token", actor=_actor())
    assert fake.kv2.calls == 1

    # invalidate + retry — back to 2 calls
    r.invalidate("vault:secret/data/api/token")
    await r.resolve("vault:secret/data/api/token", actor=_actor())
    assert fake.kv2.calls == 2


@pytest.mark.asyncio
async def test_hashicorp_resolver_rejects_non_vault_ref() -> None:
    r = HashicorpVaultSecretsResolver(url="https://vault.test", token="x")
    with pytest.raises(InvalidSecretRef):
        await r.resolve("env:HOME", actor=_actor())


@pytest.mark.asyncio
async def test_hashicorp_resolver_rejects_malformed_path() -> None:
    r = HashicorpVaultSecretsResolver(url="https://vault.test", token="x")
    with pytest.raises(InvalidSecretRef):
        await r.resolve("vault:secret", actor=_actor())


@pytest.mark.asyncio
async def test_hashicorp_resolver_missing_url_or_token_raises_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("QZDAP_VAULT_URL", raising=False)
    monkeypatch.delenv("VAULT_ADDR", raising=False)
    monkeypatch.delenv("QZDAP_VAULT_TOKEN", raising=False)
    monkeypatch.delenv("VAULT_TOKEN", raising=False)
    r = HashicorpVaultSecretsResolver()
    with pytest.raises(SecretNotFound):
        await r.resolve("vault:secret/data/x", actor=_actor())


def test_hashicorp_resolver_satisfies_protocol() -> None:
    assert isinstance(HashicorpVaultSecretsResolver(), VaultSecretsResolver)


def test_hashicorp_resolver_invalidate_clears_cache() -> None:
    r = HashicorpVaultSecretsResolver(url="x", token="y", cache_ttl_seconds=60.0)
    r._cache["secret/data/api/token"] = _fake_entry({"value": "x"})  # type: ignore[attr-defined]
    r.invalidate("vault:secret/data/api/token")
    assert "secret/data/api/token" not in r._cache  # type: ignore[attr-defined]


def _fake_entry(value: dict[str, str]) -> Any:
    from qzdap_vault.hashicorp_vault import _CacheEntry

    return _CacheEntry(value=value, expires_at=9e18)
