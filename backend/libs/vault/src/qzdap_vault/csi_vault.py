"""``csi:KEY_NAME`` → file mounted by the Vault CSI driver.

The HashiCorp Vault CSI driver (``secrets-store.csi.k8s.io`` provider
``vault``) mounts secret material at ``/vault/secrets/<KEY_NAME>`` per
k8s ``SecretProviderClass``.  Inside the pod the file content is the
*raw secret value* — no key/value envelope, no JSON.

This resolver reads ``/vault/secrets/<address>`` verbatim and returns
``{"value": <trimmed contents>}`` so it slots into the same calling
convention as :class:`FileVaultSecretsResolver` /
:meth:`resolve_value`.

Reference
---------
* https://developer.hashicorp.com/vault/docs/platform/k8s/csi
* https://secrets-store-csi-driver.sigs.k8s.io/

Security notes
--------------
* ``allowed_root`` defaults to ``/vault/secrets`` — addresses that
  escape via ``..`` raise ``SecretAccessDenied``.
* Reads are read-only; the CSI mount point is mounted ``ro`` by the
  driver so a buggy caller cannot tamper with secret material.
* For multi-tenant isolation, the caller (tool module / channel adapter)
  is responsible for verifying ``actor`` owns the secret ref before
  passing it here.  The resolver does not consult Vault policy directly.
"""

from __future__ import annotations

import os
from pathlib import Path

from qzdap_vault.actor import ActorContext
from qzdap_vault.errors import InvalidSecretRef, SecretAccessDenied, SecretNotFound
from qzdap_vault.resolver import VaultSecretsResolver, parse_ref

__all__ = ["CSIVaultSecretsResolver"]

_DEFAULT_ROOT = "/vault/secrets"


class CSIVaultSecretsResolver(VaultSecretsResolver):
    """Resolve ``csi:KEY_NAME`` from a Vault CSI driver mount.

    Parameters
    ----------
    mount_root:
        Absolute path where the CSI driver mounts secrets.  Defaults to
        ``/vault/secrets``.  Override via ``QZDAP_CSI_VAULT_ROOT`` env.
    allowed_root:
        Optional safety net — addresses must resolve under this path or
        a ``SecretAccessDenied`` is raised.  Defaults to ``mount_root``.
    """

    def __init__(
        self,
        *,
        mount_root: str | None = None,
        allowed_root: str | None = None,
    ) -> None:
        root = mount_root or os.environ.get("QZDAP_CSI_VAULT_ROOT") or _DEFAULT_ROOT
        self._mount_root = Path(root)
        self._allowed_root = (
            Path(allowed_root).resolve() if allowed_root else self._mount_root.resolve()
        )

    async def resolve(
        self,
        ref: str,
        *,
        actor: ActorContext,
    ) -> dict[str, str]:
        scheme, address = parse_ref(ref)
        if scheme != "csi":
            raise InvalidSecretRef(f"csi resolver received {scheme!r} ref")
        if not address or address.startswith("/") or "/" in address:
            raise InvalidSecretRef(
                f"csi ref must be a bare KEY_NAME under {self._mount_root}: {ref!r}"
            )
        path = self._mount_root / address
        try:
            resolved = path.resolve(strict=False)
            resolved.relative_to(self._allowed_root)
        except ValueError as exc:
            raise SecretAccessDenied(
                f"csi ref {address!r} escapes allowed_root {self._allowed_root}"
            ) from exc
        try:
            text = path.read_text(encoding="utf-8").strip()
        except FileNotFoundError as exc:
            raise SecretNotFound(
                f"csi mount has no secret at {path} (is the SecretProviderClass bound?)"
            ) from exc
        except PermissionError as exc:
            raise SecretAccessDenied(f"csi mount at {path} is not readable") from exc
        if not text:
            raise SecretNotFound(f"csi mount at {path} is empty")
        return {"value": text}
