"""Boot-time ``QZDAP_*_REF`` → ``QZDAP_*`` translation.

Why this module exists
----------------------
``Settings`` is a Pydantic ``BaseSettings`` with ``env_prefix="QZDAP_"`` and
reads each setting directly from ``os.environ["QZDAP_<FIELD>"]`` (e.g.
``database_url`` ← ``QZDAP_DATABASE_URL``).  It does NOT auto-interpret the
``QZDAP_*_REF`` indirection that ``deploy/env.prod.example`` declares.

Without this hook, env values like

    QZDAP_DATABASE_URL_REF=vault:secret/data/prod/qzdap/database_url
    QZDAP_REDIS_URL_REF=csi:QZDAP_REDIS_URL
    QZDAP_JWT_SECRET_REF=csi:QZDAP_JWT_SECRET

sit unused — Pydantic reads ``QZDAP_DATABASE_URL`` (unset → dev default)
and the prod pod silently connects to ``localhost``.

This module runs once at boot, before :func:`get_settings`.  For each
``QZDAP_*_REF`` env var it dispatches on the ref's URI prefix (``vault:``,
``csi:``, ``env:``, ``file:``, ``noop:``) and calls the matching
``VaultSecretsResolver``.  The resolved value is then injected as
``QZDAP_*`` so Pydantic sees it.

Failure mode
------------
If a ref is well-formed but the resolver raises ``SecretNotFound`` /
``SecretAccessDenied`` / ``InvalidSecretRef``, we re-raise as
``RuntimeError`` so the pod fails fast at boot instead of coming up
half-configured.
"""

from __future__ import annotations

import asyncio
import os
from typing import Final
from uuid import UUID

from qzdap_vault.actor import ActorContext
from qzdap_vault.errors import (
    InvalidSecretRef,
    SecretAccessDenied,
    SecretNotFound,
)
from qzdap_vault.resolver import VaultSecretsResolver

__all__ = ["resolve_ref_env", "resolve_ref_env_sync"]

# Env var name pattern: ``QZDAP_<UPPER_SNAKE>_REF``.  Bare counterparts
# drop the ``_REF`` suffix (``QZDAP_<UPPER_SNAKE>``).
_REF_SUFFIX: Final = "_REF"

# System actor used for boot-time resolution — no user context yet.
# Tenant/workspace UUIDs are placeholder zeros; resolvers that enforce
# actor ownership (e.g. tool-runtime secrets) are not consulted here,
# only the underlying KV / CSI / file backends.
_BOOT_ACTOR: Final = ActorContext(
    tenant_id=UUID(int=0),
    workspace_id=None,
    principal_id=None,
    roles=frozenset(),
)


def _build_resolvers() -> dict[str, VaultSecretsResolver]:
    """One resolver per scheme — lazy, fresh per process.

    ``vault`` is only constructed when the operator has supplied
    ``QZDAP_VAULT_URL`` + ``QZDAP_VAULT_TOKEN``; without those the resolver
    would just raise on every call, so we omit it and let the
    unsupported-scheme path surface the gap.
    """
    from qzdap_vault.csi_vault import CSIVaultSecretsResolver
    from qzdap_vault.env_vault import EnvVaultSecretsResolver
    from qzdap_vault.file_vault import FileVaultSecretsResolver
    from qzdap_vault.hashicorp_vault import HashicorpVaultSecretsResolver

    resolvers: dict[str, VaultSecretsResolver] = {
        "csi": CSIVaultSecretsResolver(),
        "env": EnvVaultSecretsResolver(),
        "file": FileVaultSecretsResolver(),
    }
    vault_url = os.environ.get("QZDAP_VAULT_URL", "")
    vault_token = os.environ.get("QZDAP_VAULT_TOKEN", "")
    if vault_url or vault_token:
        resolvers["vault"] = HashicorpVaultSecretsResolver(
            url=vault_url,
            token=vault_token,
            cache_ttl_seconds=30.0,
            cache_max_entries=256,
        )
    return resolvers


def _extract_value(payload: dict[str, str]) -> str:
    """Pull the canonical secret string from a resolver payload.

    Resolvers are inconsistent: ``env:`` returns ``{address: value}``,
    while ``csi:`` / ``file:`` return ``{"value": text}``.  This helper
    hides that asymmetry.
    """
    if not payload:
        raise SecretNotFound("resolver returned empty payload")
    if "value" in payload:
        return payload["value"]
    return next(iter(payload.values()))


async def resolve_ref_env() -> int:
    """Resolve every ``QZDAP_*_REF`` env var into its bare ``QZDAP_*`` twin.

    Returns the count of resolved vars (useful for boot logs / tests).

    Side effects
    ------------
    Mutates ``os.environ``: for each resolved ``QZDAP_FOO_REF`` it sets
    ``os.environ["QZDAP_FOO"]`` to the resolved value.
    """
    resolvers = _build_resolvers()
    resolved = 0

    # Snapshot keys to avoid mutation-during-iteration issues if a
    # resolver somehow writes to os.environ.
    for ref_key in [
        k for k in os.environ if k.startswith("QZDAP_") and k.endswith(_REF_SUFFIX)
    ]:
        ref = os.environ[ref_key]
        bare_key = ref_key[: -len(_REF_SUFFIX)]

        scheme, _, _ = ref.partition(":")
        if scheme not in resolvers:
            # Unknown / unsupported scheme. In dev/test/ci we leave the
            # var untouched — operators legitimately set
            # ``QZDAP_*_REF`` to literal placeholders there. In
            # production / staging we fail-loud: a misconfigured
            # scheme means the resolved secret will never land, which
            # downstream code would then read as an empty / sentinel
            # value and silently degrade.
            from os import getenv as _getenv

            if _getenv("QZDAP_ENV", "development") in {"production", "staging"}:
                raise RuntimeError(
                    f"boot: unknown QZDAP_*_REF scheme {scheme!r} in "
                    f"{ref_key}={ref!r}. Known schemes: "
                    f"{sorted(resolvers)}"
                )
            continue
        resolver = resolvers[scheme]
        try:
            payload = await resolver.resolve(ref, actor=_BOOT_ACTOR)
        except (SecretNotFound, SecretAccessDenied, InvalidSecretRef) as exc:
            raise RuntimeError(
                f"boot: failed to resolve {ref_key}={ref!r}: {exc}"
            ) from exc
        os.environ[bare_key] = _extract_value(payload)
        resolved += 1

    return resolved


def resolve_ref_env_sync() -> int:
    """Synchronous wrapper for boot-time use.

    ``create_app()`` is normally invoked before uvicorn / gunicorn
    starts its event loop, so we drive ``resolve_ref_env`` via
    :func:`asyncio.run`. Under ``uvicorn --reload`` the app factory is
    called *inside* a running loop (the reloader subprocess), so we
    cannot reuse it. Instead we spin up a dedicated loop on a side
    thread — a fresh event loop lets us ``run_until_complete`` the
    coroutine to completion without colliding with the caller's loop.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(resolve_ref_env())
    # Running inside an event loop — drive the coroutine on a fresh
    # loop so we don't violate the "no nested loops" invariant.
    import threading

    holder: list[int] = []
    exc: list[BaseException] = []

    def _worker() -> None:
        new_loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(new_loop)
            holder.append(new_loop.run_until_complete(resolve_ref_env()))
        except BaseException as e:  # pragma: no cover - propagated below  # noqa: BLE001
            exc.append(e)
        finally:
            new_loop.close()

    t = threading.Thread(target=_worker, name="qzdap-boot-ref-resolver", daemon=True)
    t.start()
    t.join()
    if exc:
        raise exc[0]
    return holder[0]
