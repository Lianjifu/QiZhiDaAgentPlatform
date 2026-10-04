"""``env:KEY_NAME`` → ``{KEY_NAME: os.environ[KEY_NAME]}``.

For each ``ref`` we look up a single env var named after the address and
return a one-key dict whose key is the env-var name.  This keeps the
naming consistent (the header name / token name can be derived from the
same string) and avoids surprises from arbitrary ``os.environ`` leakage.

Security note (P5 doc): the env var itself is the secret.  The plan
documents that ``actor`` ownership is enforced at the *call site* (the
tool module is responsible for verifying ``actor`` owns the secret_ref),
not by the resolver.  See ``doc/backend/12-实施计划.md`` §P5.
"""

from __future__ import annotations

import os

from qzdap_vault.actor import ActorContext
from qzdap_vault.errors import InvalidSecretRef, SecretNotFound
from qzdap_vault.resolver import VaultSecretsResolver, parse_ref

__all__ = ["EnvVaultSecretsResolver"]


class EnvVaultSecretsResolver(VaultSecretsResolver):
    """Resolve ``env:KEY`` by reading the named environment variable."""

    async def resolve(
        self,
        ref: str,
        *,
        actor: ActorContext,
    ) -> dict[str, str]:
        scheme, address = parse_ref(ref)
        if scheme != "env":
            raise InvalidSecretRef(f"env resolver received {scheme!r} ref")
        try:
            value = os.environ[address]
        except KeyError as exc:
            raise SecretNotFound(f"env var {address!r} is not set") from exc
        return {address: value}
