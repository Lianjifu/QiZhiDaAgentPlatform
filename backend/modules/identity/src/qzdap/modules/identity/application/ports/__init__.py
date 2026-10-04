"""Application-layer ports (interfaces).

The adapter package implements these; use cases depend ONLY on ports.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any
from uuid import UUID

from qzdap.modules.identity.domain import APIKey, Tenant, User, Workspace


class TenantRepository(ABC):
    @abstractmethod
    async def add(self, tenant: Tenant) -> None: ...
    @abstractmethod
    async def get(self, tenant_id: UUID) -> Tenant | None: ...
    @abstractmethod
    async def get_by_slug(self, slug: str) -> Tenant | None: ...


class WorkspaceRepository(ABC):
    @abstractmethod
    async def add(self, workspace: Workspace) -> None: ...
    @abstractmethod
    async def get(self, workspace_id: UUID) -> Workspace | None: ...
    @abstractmethod
    async def list_for_tenant(
        self, tenant_id: UUID, limit: int, offset: int
    ) -> list[Workspace]: ...
    @abstractmethod
    async def count_for_tenant(self, tenant_id: UUID) -> int: ...


class UserRepository(ABC):
    @abstractmethod
    async def add(self, user: User) -> None: ...
    @abstractmethod
    async def get(self, user_id: UUID) -> User | None: ...
    @abstractmethod
    async def get_by_email(self, tenant_id: UUID, email: str) -> User | None: ...
    @abstractmethod
    async def get_by_email_global(self, email: str) -> User | None:
        """Cross-tenant email lookup.

        Used by the login flow when the caller does not know the tenant_id
        ahead of time (typical for first-touch credential auth). Assumes
        email is globally unique across tenants — a precondition enforced
        upstream by the registration flow. Returns the first match if
        multiple exist (TODO: harden once a global uniqueness constraint
        lands on `users.email`).
        """
        ...


class APIKeyRepository(ABC):
    @abstractmethod
    async def add(self, api_key: APIKey) -> None: ...
    @abstractmethod
    async def get(self, api_key_id: UUID) -> APIKey | None: ...
    @abstractmethod
    async def list_for_owner(self, user_id: UUID) -> list[APIKey]: ...


class Hasher(ABC):
    @abstractmethod
    def hash(self, raw: str) -> str: ...

    @abstractmethod
    def verify(self, raw: str, hashed: str) -> bool: ...


class AccessTokenIssuer(ABC):
    @abstractmethod
    def issue(self, user: User, workspace_id: Any) -> tuple[str, int]: ...
