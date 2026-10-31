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

from qzdap_kernel.ids import TenantId, WorkspaceId


@dataclass(slots=True, frozen=True)
class ActorContext:
    """The actor requesting secret material.

    ``tenant_id`` is required; ``workspace_id`` and ``principal_id`` are
    optional but recommended.  A resolver MAY raise ``SecretAccessDenied``
    when these are missing.

    ⚠️ **租户 / 工作区用品牌 ID** ✓（`TenantId` / `WorkspaceId` ✓）—— 这是
    「**身份上下文 → 应用层**」的那道边界 ✓：**裸 `UUID` 只允许出现在最外层**
    （JWT 解析 / HTTP 参数 / DB 行 ✓）→ **进到这里之前就转好** ✓。
    """

    tenant_id: TenantId
    workspace_id: WorkspaceId | None = None
    principal_id: UUID | None = None
    roles: frozenset[str] = frozenset()

    @classmethod
    def anonymous(cls, *, tenant_id: TenantId) -> ActorContext:
        return cls(tenant_id=tenant_id)


__all__ = ["ActorContext"]
