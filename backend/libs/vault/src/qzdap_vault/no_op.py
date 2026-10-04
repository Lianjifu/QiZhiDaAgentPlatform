"""``noop:...`` → ``{}``.

Always returns an empty dict.  Used by tests and by the ``default``
composition when no real vault is configured (no secrets env vars set).

Note that this does NOT raise ``SecretNotFound`` — the noop resolver
pretends every ref exists but yields nothing.  This matches the existing
tool-module `_no_op_secrets_resolver` behaviour.
"""

from __future__ import annotations

from qzdap_vault.actor import ActorContext
from qzdap_vault.resolver import VaultSecretsResolver

__all__ = ["NoOpSecretsResolver"]


class NoOpSecretsResolver(VaultSecretsResolver):
    """Returns an empty dict for any ref.  Never raises."""

    async def resolve(
        self,
        ref: str,
        *,
        actor: ActorContext,
    ) -> dict[str, str]:
        return {}
