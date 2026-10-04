"""In-memory adapters for the application ports — used by unit tests."""

from __future__ import annotations

from collections import defaultdict
from typing import Any
from uuid import UUID

from qzdap.modules.identity.application.ports import (
    APIKeyRepository,
    Hasher,
    TenantRepository,
    UserRepository,
    WorkspaceRepository,
)
from qzdap.modules.identity.domain import APIKey, Tenant, User, Workspace


class InMemoryTenantRepository(TenantRepository):
    def __init__(self) -> None:
        self._by_id: dict[UUID, Tenant] = {}

    async def add(self, tenant: Tenant) -> None:
        if any(t.slug == tenant.slug for t in self._by_id.values()):
            from qzdap.modules.identity.domain.errors import TenantAlreadyExists

            raise TenantAlreadyExists(f"slug {tenant.slug!r} already exists")
        self._by_id[tenant.id] = tenant

    async def get(self, tenant_id: UUID) -> Tenant | None:
        return self._by_id.get(tenant_id)

    async def get_by_slug(self, slug: str) -> Tenant | None:
        return next((t for t in self._by_id.values() if t.slug == slug), None)


class InMemoryWorkspaceRepository(WorkspaceRepository):
    def __init__(self) -> None:
        self._by_id: dict[UUID, Workspace] = {}

    async def add(self, workspace: Workspace) -> None:
        self._by_id[workspace.id] = workspace

    async def get(self, workspace_id: UUID) -> Workspace | None:
        return self._by_id.get(workspace_id)

    async def list_for_tenant(
        self, tenant_id: UUID, limit: int, offset: int
    ) -> list[Workspace]:
        items = [w for w in self._by_id.values() if w.tenant_id == tenant_id]
        return items[offset : offset + limit]

    async def count_for_tenant(self, tenant_id: UUID) -> int:
        return sum(1 for w in self._by_id.values() if w.tenant_id == tenant_id)


class InMemoryUserRepository(UserRepository):
    def __init__(self) -> None:
        self._by_id: dict[UUID, User] = {}
        self._by_tenant_email: dict[tuple[UUID, str], UUID] = {}

    async def add(self, user: User) -> None:
        key = (user.tenant_id, user.email)
        if key in self._by_tenant_email:
            from qzdap.modules.identity.domain.errors import UserAlreadyExists

            raise UserAlreadyExists(f"email {user.email!r} already exists")
        self._by_id[user.id] = user
        self._by_tenant_email[key] = user.id

    async def get(self, user_id: UUID) -> User | None:
        return self._by_id.get(user_id)

    async def get_by_email(self, tenant_id: UUID, email: str) -> User | None:
        uid = self._by_tenant_email.get((tenant_id, email.lower()))
        return self._by_id.get(uid) if uid else None

    async def get_by_email_global(self, email: str) -> User | None:
        # First match across tenants. Email global uniqueness is enforced
        # upstream by the registration flow.
        email_lower = email.lower()
        for uid in self._by_tenant_email.values():
            user = self._by_id.get(uid)
            if user is not None and user.email.lower() == email_lower:
                return user
        return None


class InMemoryAPIKeyRepository(APIKeyRepository):
    def __init__(self) -> None:
        self._by_id: dict[UUID, APIKey] = {}

    async def add(self, api_key: APIKey) -> None:
        self._by_id[api_key.id] = api_key

    async def get(self, api_key_id: UUID) -> APIKey | None:
        return self._by_id.get(api_key_id)

    async def list_for_owner(self, user_id: UUID) -> list[APIKey]:
        return [k for k in self._by_id.values() if k.owner_user_id == user_id]

    async def update(self, api_key: APIKey) -> None:
        self._by_id[api_key.id] = api_key


class FakeHasher(Hasher):
    """Reversible hasher (DO NOT USE IN PROD). Only for tests."""

    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    def hash(self, raw: str) -> str:
        h = f"fake:{raw}"
        self._store[h] = raw
        return h

    def verify(self, raw: str, hashed: str) -> bool:
        return self._store.get(hashed) == raw


class FakeAccessTokenIssuer:
    def __init__(self) -> None:
        self.issued: list[tuple[Any, Any]] = []

    def issue(self, user: Any, workspace_id: Any) -> tuple[str, int]:
        self.issued.append((user, workspace_id))
        return f"token-{user.id}", 9999999999


# Convenience factory
def make_repositories():  # type: ignore[no-untyped-def]
    return {
        "tenants": InMemoryTenantRepository(),
        "workspaces": InMemoryWorkspaceRepository(),
        "users": InMemoryUserRepository(),
        "api_keys": InMemoryAPIKeyRepository(),
        "hasher": FakeHasher(),
        "issuer": FakeAccessTokenIssuer(),
    }


# Keep dict access type-safe at call sites
_ = defaultdict
