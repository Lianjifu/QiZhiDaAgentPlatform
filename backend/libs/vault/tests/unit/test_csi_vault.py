"""Unit tests for the CSI Vault driver resolver.

The CSI driver mounts secrets at ``/vault/secrets/<KEY>`` inside the pod.
We don't ship a real CSI driver in CI; instead these tests use a tmp
directory as the mount root and verify the resolver's contract.
"""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

import pytest

from qzdap_vault import (
    ActorContext,
    CSIVaultSecretsResolver,
    InvalidSecretRef,
    SecretNotFound,
    VaultSecretsResolver,
    resolve_value,
)


def _actor() -> ActorContext:
    return ActorContext(tenant_id=UUID(int=1), workspace_id=UUID(int=2))


# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_csi_resolver_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "API_TOKEN").write_text("supersecret\n")
    monkeypatch.setenv("QZDAP_CSI_VAULT_ROOT", str(tmp_path))

    r = CSIVaultSecretsResolver()
    payload = await r.resolve("csi:API_TOKEN", actor=_actor())
    assert payload == {"value": "supersecret"}


@pytest.mark.asyncio
async def test_csi_resolver_missing_file_raises(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("QZDAP_CSI_VAULT_ROOT", str(tmp_path))
    r = CSIVaultSecretsResolver()
    with pytest.raises(SecretNotFound):
        await r.resolve("csi:NEVER_MOUNTED", actor=_actor())


@pytest.mark.asyncio
async def test_csi_resolver_empty_file_raises(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "EMPTY").write_text("   \n")
    monkeypatch.setenv("QZDAP_CSI_VAULT_ROOT", str(tmp_path))
    r = CSIVaultSecretsResolver()
    with pytest.raises(SecretNotFound):
        await r.resolve("csi:EMPTY", actor=_actor())


@pytest.mark.asyncio
async def test_csi_resolver_rejects_absolute_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("QZDAP_CSI_VAULT_ROOT", str(tmp_path))
    r = CSIVaultSecretsResolver()
    with pytest.raises(InvalidSecretRef):
        await r.resolve("csi:/etc/passwd", actor=_actor())


@pytest.mark.asyncio
async def test_csi_resolver_rejects_traversal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real = tmp_path / "REAL.txt"
    real.write_text("ok")
    sibling = tmp_path.parent / "EVIL.txt"
    sibling.write_text("evil")

    monkeypatch.setenv("QZDAP_CSI_VAULT_ROOT", str(tmp_path))
    r = CSIVaultSecretsResolver()
    # CSI addresses are bare key names — `..` is rejected up-front
    # (path-traversal is a defence-in-depth that follows in the resolve).
    with pytest.raises(InvalidSecretRef):
        await r.resolve("csi:../EVIL.txt", actor=_actor())

    # A flat name that exists inside the mount reads OK.
    payload = await r.resolve("csi:REAL.txt", actor=_actor())
    assert payload["value"] == "ok"


@pytest.mark.asyncio
async def test_csi_resolver_rejects_non_csi_ref(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("QZDAP_CSI_VAULT_ROOT", str(tmp_path))
    r = CSIVaultSecretsResolver()
    with pytest.raises(InvalidSecretRef):
        await r.resolve("env:HOME", actor=_actor())


def test_csi_resolver_satisfies_protocol() -> None:
    assert isinstance(CSIVaultSecretsResolver(), VaultSecretsResolver)


@pytest.mark.asyncio
async def test_csi_resolve_value_helper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "KEY").write_text("the-value")
    monkeypatch.setenv("QZDAP_CSI_VAULT_ROOT", str(tmp_path))
    r = CSIVaultSecretsResolver()
    out = await resolve_value(r, "csi:KEY", actor=_actor())
    assert out == "the-value"
