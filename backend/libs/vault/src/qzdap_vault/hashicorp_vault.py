"""``vault:<path>`` → HashiCorp Vault KV v2 lookup.

References take the form ``vault:secret/data/<path>`` (KV v2 API) or
``vault:<mount>/data/<key>`` for non-default mounts.  The resolver
returns the latest version of the secret as a ``{key: value}`` dict.

Design notes
------------
* The ``hvac`` client is imported lazily inside ``__init__`` so the
  dependency stays optional — devs / CI without HashiCorp Vault can
  install ``qzdap-vault`` without pulling ``hvac``.
* An in-process ``TTLCache`` (per resolver instance) keeps a hot path
  fast — the same ``ref`` resolved twice within ``cache_ttl`` seconds
  does not re-hit Vault.  This mirrors the model_credentials decrypt
  cache the rest of the codebase uses.
* Tokens come from ``VAULT_TOKEN`` (and ``VAULT_NAMESPACE`` /
  ``VAULT_URL`` / ``VAULT_MOUNT``) — never logged.
* On ``hvac.exceptions.InvalidPath`` we raise ``SecretNotFound``; on
  ``hvac.exceptions.Forbidden`` we raise ``SecretAccessDenied``; on
  transport errors we re-raise as ``SecretNotFound`` with the original
  message so callers see one stable error family.
"""

from __future__ import annotations

import asyncio
import importlib
import time
from dataclasses import dataclass, field
from threading import Lock
from typing import Any

from qzdap_vault.actor import ActorContext
from qzdap_vault.errors import InvalidSecretRef, SecretAccessDenied, SecretNotFound
from qzdap_vault.resolver import VaultSecretsResolver, parse_ref

__all__ = ["HashicorpVaultSecretsResolver"]


def _load_hvac() -> Any:
    """Lazily import hvac so the dep stays optional (install qzdap-vault[hashicorp])."""
    try:
        return importlib.import_module("hvac")
    except ModuleNotFoundError as exc:  # pragma: no cover - import guard
        raise SecretNotFound(
            "hashicorp vault resolver requires the 'hvac' extra: "
            "uv pip install 'qzdap-vault[hashicorp]'"
        ) from exc


@dataclass(slots=True)
class _CacheEntry:
    value: dict[str, str]
    expires_at: float


@dataclass(slots=True)
class HashicorpVaultSecretsResolver(VaultSecretsResolver):
    """Resolve ``vault:<path>`` via HashiCorp Vault KV v2.

    Parameters
    ----------
    url:
        Vault server URL (e.g. ``https://vault.svc:8200``).  Falls back
        to ``QZDAP_VAULT_URL`` and then to ``VAULT_ADDR``.
    token:
        Vault token.  Falls back to ``QZDAP_VAULT_TOKEN`` and then to
        ``VAULT_TOKEN``.  When neither is set the resolver raises
        ``SecretNotFound`` on the first ``resolve`` call (so a misconfig
        does NOT silently leak data).
    namespace:
        Optional Vault Enterprise namespace.  ``VAULT_NAMESPACE`` env
        is consulted first.
    mount_point:
        KV v2 mount, default ``"secret"``.  ``QZDAP_VAULT_MOUNT`` env
        overrides.
    cache_ttl_seconds:
        Hot-path cache TTL.  ``0`` disables caching.
    cache_max_entries:
        LRU cap for the in-process cache.
    """

    url: str | None = None
    token: str | None = None
    namespace: str | None = None
    mount_point: str | None = None
    cache_ttl_seconds: float = 30.0
    cache_max_entries: int = 256

    _client: Any = field(default=None, init=False, repr=False)
    _cache: dict[str, _CacheEntry] = field(default_factory=dict, init=False, repr=False)
    _lock: Lock = field(default_factory=Lock, init=False, repr=False)

    # ---- public API -------------------------------------------------------

    async def resolve(
        self,
        ref: str,
        *,
        actor: ActorContext,
    ) -> dict[str, str]:
        scheme, address = parse_ref(ref)
        if scheme != "vault":
            raise InvalidSecretRef(f"vault resolver received {scheme!r} ref")
        if not address or "/" not in address:
            raise InvalidSecretRef(
                f"vault ref must be '<mount>/data/<path>' or 'secret/data/<path>': {ref!r}"
            )

        cached = self._cache_get(address)
        if cached is not None:
            return dict(cached)

        client = self._ensure_client()
        mount, kv_path = self._split_address(address)
        payload = await asyncio.to_thread(self._read_secret, client, mount, kv_path)
        self._cache_put(address, payload)
        return dict(payload)

    def invalidate(self, ref: str | None = None) -> None:
        """Drop one or all cached entries.  Use after a Vault rotate."""
        with self._lock:
            if ref is None:
                self._cache.clear()
                return
            scheme, address = parse_ref(ref)
            if scheme != "vault":
                return
            self._cache.pop(address, None)

    # ---- internals --------------------------------------------------------

    def _ensure_client(self) -> Any:
        if self._client is not None:
            return self._client

        import os

        hvac = _load_hvac()
        url = (
            self.url or os.environ.get("QZDAP_VAULT_URL") or os.environ.get("VAULT_ADDR")
        )
        token = (
            self.token
            or os.environ.get("QZDAP_VAULT_TOKEN")
            or os.environ.get("VAULT_TOKEN")
        )
        if not url:
            raise SecretNotFound("vault resolver: VAULT_ADDR / QZDAP_VAULT_URL not set")
        if not token:
            raise SecretNotFound(
                "vault resolver: VAULT_TOKEN / QZDAP_VAULT_TOKEN not set"
            )
        ns = self.namespace or os.environ.get("VAULT_NAMESPACE")
        client = hvac.Client(url=url, token=token, namespace=ns)
        self._client = client
        return client

    def _mount_point(self) -> str:
        import os

        return self.mount_point or os.environ.get("QZDAP_VAULT_MOUNT") or "secret"

    def _split_address(self, address: str) -> tuple[str, str]:
        """Resolve ``<mount>/data/<rest>`` → ``(mount, <rest>)``.

        The mount segment of the address, if present, overrides the
        resolver's default mount.  Bare ``<rest>`` (no ``data`` segment)
        uses the default mount.
        """
        default_mount = self._mount_point()
        parts = address.split("/")
        if len(parts) >= 3 and parts[1] == "data":
            mount = parts[0] or default_mount
            rest = "/".join(parts[2:])
            if not rest:
                raise InvalidSecretRef(
                    f"vault ref missing path after 'data': {address!r}"
                )
            return mount, rest
        return default_mount, address

    @staticmethod
    def _read_secret(
        client: Any,
        mount: str,
        path: str,
    ) -> dict[str, str]:
        """Synchronous hvac read — wrapped in ``asyncio.to_thread`` by the caller."""
        try:
            resp = client.secrets.kv.v2.read_secret(path=path, mount_point=mount)
        except Exception as exc:  # hvac exception tree varies; map to vault errors
            name = type(exc).__name__
            if name in {"InvalidPath", "VaultNotFound"} or "InvalidPath" in name:
                raise SecretNotFound(f"vault: no secret at {mount}/{path}") from exc
            if name in {"Forbidden", "PermissionDenied"} or "Forbidden" in name:
                raise SecretAccessDenied(
                    f"vault: token denied for {mount}/{path}"
                ) from exc
            raise SecretNotFound(
                f"vault read failed for {mount}/{path}: {exc}"
            ) from exc

        data = (resp or {}).get("data") or {}
        if "data" in data and isinstance(data["data"], dict):
            data = data["data"]
        out: dict[str, str] = {}
        for k, v in data.items():
            out[k] = "" if v is None else str(v)
        if not out:
            raise SecretNotFound(f"vault: empty payload at {mount}/{path}")
        return out

    def _cache_get(self, address: str) -> dict[str, str] | None:
        if self.cache_ttl_seconds <= 0:
            return None
        now = time.monotonic()
        with self._lock:
            entry = self._cache.get(address)
            if entry is None:
                return None
            if entry.expires_at <= now:
                self._cache.pop(address, None)
                return None
            return entry.value

    def _cache_put(self, address: str, value: dict[str, str]) -> None:
        if self.cache_ttl_seconds <= 0:
            return
        with self._lock:
            if len(self._cache) >= self.cache_max_entries:
                oldest = next(iter(self._cache))
                self._cache.pop(oldest, None)
            self._cache[address] = _CacheEntry(
                value=dict(value),
                expires_at=time.monotonic() + self.cache_ttl_seconds,
            )
