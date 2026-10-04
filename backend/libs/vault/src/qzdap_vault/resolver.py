"""Secrets resolver Protocol.

``ref`` strings look like ``"<scheme>:<address>"``:

- ``env:KEY_NAME``            — read ``os.environ["KEY_NAME"]``
- ``file:/absolute/path``     — read the file at the given path
- ``noop:anything``           — always returns an empty dict (test/dev)
- ``vault:secret/data/PATH``  — HashiCorp Vault KV v2 lookup (requires ``hvac``)
- ``csi:MY_SECRET``           — read ``/vault/secrets/MY_SECRET`` mounted by the
                                Vault CSI driver (k8s)

Each resolver returns a ``dict[str, str]`` so a single ``ref`` can carry
multiple values (e.g. ``env:API_KEY`` → ``{"api_key": "..."}`` — the env
var name becomes the dict key).

The Protocol also accepts a legacy single-value path: callers that only
care about one string can call ``await resolver.resolve_value(ref, ...)``
which reads ``result["value"]`` (i.e. the env-var-named ``value``).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from qzdap_vault.actor import ActorContext
from qzdap_vault.errors import InvalidSecretRef, SecretNotFound

__all__ = ["SecretRef", "VaultSecretsResolver", "parse_ref", "resolve_value"]


class SecretRef(str):
    """Validated reference string.  Construct via :func:`parse_ref`."""


_SUPPORTED_SCHEMES: frozenset[str] = frozenset({"env", "file", "noop", "vault", "csi"})


def parse_ref(ref: str) -> tuple[str, str]:
    """Split ``"<scheme>:<address>"`` into ``(scheme, address)``.

    Raises ``InvalidSecretRef`` when the string does not look like a ref.
    """
    if not ref or ":" not in ref:
        raise InvalidSecretRef(f"missing scheme: {ref!r}")
    scheme, _, address = ref.partition(":")
    if not scheme or not address:
        raise InvalidSecretRef(f"empty scheme or address: {ref!r}")
    if scheme not in _SUPPORTED_SCHEMES:
        raise InvalidSecretRef(f"unsupported scheme: {scheme!r}")
    return scheme, address


@runtime_checkable
class VaultSecretsResolver(Protocol):
    """Resolves a ``ref`` to a dict of named secret values.

    Implementations are responsible for enforcing actor ownership and
    backend-specific access controls.  They MUST raise
    :class:`SecretNotFound` when the ref is well-formed but unknown, and
    :class:`SecretAccessDenied` when the actor lacks permission.
    """

    async def resolve(
        self,
        ref: str,
        *,
        actor: ActorContext,
    ) -> dict[str, str]: ...


async def resolve_value(
    resolver: VaultSecretsResolver,
    ref: str,
    *,
    actor: ActorContext,
) -> str:
    """Helper: resolve and pull the single ``"value"`` key.

    Raises ``SecretNotFound`` if the resolver returned an empty dict.
    """
    payload = await resolver.resolve(ref, actor=actor)
    try:
        return payload["value"]
    except KeyError as exc:
        raise SecretNotFound(f"ref {ref!r} did not yield a 'value' key") from exc
