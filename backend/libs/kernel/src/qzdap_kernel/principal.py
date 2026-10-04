"""Principal: who is making the request.

A Principal is the authenticated entity (User, ServiceAccount, or APIKey). It
carries the tenant and workspace context, and a set of role/scopes used by
authorization checks downstream.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Self
from uuid import UUID


class PrincipalType(StrEnum):
    USER = "user"
    SERVICE_ACCOUNT = "service_account"
    API_KEY = "api_key"
    SYSTEM = "system"  # background jobs, root-owned


@dataclass(slots=True, frozen=True)
class Principal:
    """The authenticated entity making the request.

    Attributes:
        id: Stable opaque identifier (user_id / sa_id / api_key_id).
        type: How the principal authenticated.
        tenant_id: Tenant the principal belongs to. Required for all
            non-system principals.
        workspace_id: Workspace within the tenant. None means tenant-wide.
        roles: Set of role strings (e.g. "platform_admin", "workspace_owner").
        scopes: Set of OAuth-style scopes.
        display_name: Optional human-readable label, used in logs / audit.
    """

    id: UUID
    type: PrincipalType
    tenant_id: UUID | None
    workspace_id: UUID | None
    roles: frozenset[str] = field(default_factory=frozenset)
    scopes: frozenset[str] = field(default_factory=frozenset)
    display_name: str | None = None

    def __post_init__(self) -> None:
        if self.type is not PrincipalType.SYSTEM and self.tenant_id is None:
            raise ValueError(f"{self.type} principal requires tenant_id")
        if not isinstance(self.roles, frozenset):
            object.__setattr__(self, "roles", frozenset(self.roles))
        if not isinstance(self.scopes, frozenset):
            object.__setattr__(self, "scopes", frozenset(self.scopes))

    def with_workspace(self, workspace_id: UUID | None) -> Self:
        """Return a copy scoped to a different workspace."""
        return type(self)(
            id=self.id,
            type=self.type,
            tenant_id=self.tenant_id,
            workspace_id=workspace_id,
            roles=self.roles,
            scopes=self.scopes,
            display_name=self.display_name,
        )

    def has_role(self, role: str) -> bool:
        return role in self.roles

    def has_scope(self, scope: str) -> bool:
        return scope in self.scopes

    def is_platform_admin(self) -> bool:
        return "platform_admin" in self.roles

    @classmethod
    def system(cls, *, roles: frozenset[str] | None = None) -> Self:
        return cls(
            id=UUID(int=0),
            type=PrincipalType.SYSTEM,
            tenant_id=None,
            workspace_id=None,
            roles=roles or frozenset({"platform_internal"}),
        )
