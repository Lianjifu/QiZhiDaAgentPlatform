"""``file:/path`` → ``{"value": contents}``.

Reads the file at the given absolute path and returns its trimmed
contents.  We do NOT parse the file as JSON — secrets live as raw
strings (often opaque tokens) and YAML/INI parsing would over-promise.

Path safety: addresses are passed through verbatim.  Callers are
expected to whitelist allowed paths (e.g. via an ``allowed_root``
setting).  When ``allowed_root`` is set, addresses that escape it raise
``SecretAccessDenied``.
"""

from __future__ import annotations

from pathlib import Path

from qzdap_vault.actor import ActorContext
from qzdap_vault.errors import InvalidSecretRef, SecretAccessDenied, SecretNotFound
from qzdap_vault.resolver import VaultSecretsResolver, parse_ref

__all__ = ["FileVaultSecretsResolver"]


class FileVaultSecretsResolver(VaultSecretsResolver):
    """Resolve ``file:/absolute/path`` by reading the file contents."""

    def __init__(self, *, allowed_root: str | None = None) -> None:
        self._allowed_root = Path(allowed_root).resolve() if allowed_root else None

    async def resolve(
        self,
        ref: str,
        *,
        actor: ActorContext,
    ) -> dict[str, str]:
        scheme, address = parse_ref(ref)
        if scheme != "file":
            raise InvalidSecretRef(f"file resolver received {scheme!r} ref")
        path = Path(address)
        if self._allowed_root is not None:
            try:
                resolved = path.resolve()
                resolved.relative_to(self._allowed_root)
            except ValueError as exc:
                raise SecretAccessDenied(
                    f"path {address!r} escapes allowed_root"
                ) from exc
        try:
            text = path.read_text(encoding="utf-8").strip()
        except FileNotFoundError as exc:
            raise SecretNotFound(f"file {address!r} does not exist") from exc
        return {"value": text}
