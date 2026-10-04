"""Unit tests for libs/vault — parse_ref + three resolvers."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from qzdap_vault import (
    ActorContext,
    EnvVaultSecretsResolver,
    FileVaultSecretsResolver,
    InvalidSecretRef,
    NoOpSecretsResolver,
    SecretAccessDenied,
    SecretNotFound,
    VaultSecretsResolver,
    parse_ref,
    resolve_value,
)


def _actor() -> ActorContext:
    from uuid import UUID

    return ActorContext(tenant_id=UUID(int=1), workspace_id=UUID(int=2))


# parse_ref -----------------------------------------------------------------


def test_parse_ref_env() -> None:
    assert parse_ref("env:FOO") == ("env", "FOO")


def test_parse_ref_file() -> None:
    assert parse_ref("file:/etc/secrets/key") == ("file", "/etc/secrets/key")


def test_parse_ref_vault() -> None:
    assert parse_ref("vault:secret/data/api/token") == (
        "vault",
        "secret/data/api/token",
    )


def test_parse_ref_csi() -> None:
    assert parse_ref("csi:API_TOKEN") == ("csi", "API_TOKEN")


def test_parse_ref_rejects_empty() -> None:
    with pytest.raises(InvalidSecretRef):
        parse_ref("")


def test_parse_ref_rejects_no_colon() -> None:
    with pytest.raises(InvalidSecretRef):
        parse_ref("envFOO")


def test_parse_ref_rejects_unknown_scheme() -> None:
    with pytest.raises(InvalidSecretRef):
        parse_ref("aws:KEY")


# EnvVaultSecretsResolver ---------------------------------------------------


@pytest.mark.asyncio
async def test_env_resolver_reads_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QZDAP_TEST_SECRET_X", "shh")
    r = EnvVaultSecretsResolver()
    payload = await r.resolve("env:QZDAP_TEST_SECRET_X", actor=_actor())
    assert payload == {"QZDAP_TEST_SECRET_X": "shh"}


@pytest.mark.asyncio
async def test_env_resolver_missing_var_raises() -> None:
    r = EnvVaultSecretsResolver()
    with pytest.raises(SecretNotFound):
        await r.resolve("env:QZDAP_TEST_SECRET_DEFINITELY_NOT_SET", actor=_actor())


@pytest.mark.asyncio
async def test_env_resolver_rejects_non_env_ref() -> None:
    r = EnvVaultSecretsResolver()
    with pytest.raises(InvalidSecretRef):
        await r.resolve("file:/tmp/x", actor=_actor())


# FileVaultSecretsResolver --------------------------------------------------


@pytest.mark.asyncio
async def test_file_resolver_reads(tmp_path: Path) -> None:
    p = tmp_path / "key.txt"
    p.write_text("hello\n")
    r = FileVaultSecretsResolver()
    payload = await r.resolve(f"file:{p}", actor=_actor())
    assert payload == {"value": "hello"}


@pytest.mark.asyncio
async def test_file_resolver_missing_raises(tmp_path: Path) -> None:
    r = FileVaultSecretsResolver()
    with pytest.raises(SecretNotFound):
        await r.resolve(f"file:{tmp_path / 'absent'}", actor=_actor())


@pytest.mark.asyncio
async def test_file_resolver_allowed_root_blocks_escape(tmp_path: Path) -> None:
    inside = tmp_path / "ok.txt"
    inside.write_text("ok")
    outside = tmp_path.parent / "evil.txt"
    outside.write_text("evil")

    r = FileVaultSecretsResolver(allowed_root=str(tmp_path))
    payload = await r.resolve(f"file:{inside}", actor=_actor())
    assert payload["value"] == "ok"
    with pytest.raises(SecretAccessDenied):
        await r.resolve(f"file:{outside}", actor=_actor())


# NoOpSecretsResolver -------------------------------------------------------


@pytest.mark.asyncio
async def test_noop_resolver_always_empty() -> None:
    r = NoOpSecretsResolver()
    payload = await r.resolve("anything:here", actor=_actor())
    assert payload == {}


# Protocol structural typing -----------------------------------------------


def test_resolvers_satisfy_protocol() -> None:
    """All three implementations must be runtime-checkable as VaultSecretsResolver."""
    assert isinstance(EnvVaultSecretsResolver(), VaultSecretsResolver)
    assert isinstance(NoOpSecretsResolver(), VaultSecretsResolver)
    assert isinstance(FileVaultSecretsResolver(), VaultSecretsResolver)


# resolve_value helper ------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_value_returns_value_key() -> None:
    r = FileVaultSecretsResolver()

    class _TmpFile:
        pass

    import tempfile

    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        f.write("abc")
        path = f.name
    try:
        out = await resolve_value(r, f"file:{path}", actor=_actor())
    finally:
        os.unlink(path)
    assert out == "abc"


@pytest.mark.asyncio
async def test_resolve_value_raises_when_no_value_key() -> None:
    r = NoOpSecretsResolver()
    with pytest.raises(SecretNotFound):
        await resolve_value(r, "noop:x", actor=_actor())
