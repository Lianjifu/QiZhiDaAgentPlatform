"""Actor context passed to a SecretsResolver.

A ``VaultSecretsResolver`` is given an ``ActorContext`` so that the resolver
can enforce ownership (e.g. a workspace API key is only resolvable by the
actor that belongs to the same workspace).

The fields are intentionally minimal. Authentication populates this from
the JWT/API-key middleware — see ``qzdap_auth.dependencies``.

Why not pass the full ``Principal``?  The vault layer should not depend on
the auth module.  ``ActorContext`` is the smallest projection that the
secrets contract needs.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


@dataclass(slots=True, frozen=True)
class ActorContext:
    """The actor requesting secret material.

    ``tenant_id`` is required; ``workspace_id`` and ``principal_id`` are
    optional but recommended.  A resolver MAY raise ``SecretAccessDenied``
    when these are missing.
    """

    tenant_id: UUID
    workspace_id: UUID | None = None
    principal_id: UUID | None = None
    roles: frozenset[str] = frozenset()

    @classmethod
    def anonymous(cls, *, tenant_id: UUID) -> ActorContext:
        return cls(tenant_id=tenant_id)


__all__ = ["ActorContext"]
