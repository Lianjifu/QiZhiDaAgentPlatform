"""SQLAlchemy repository implementations of the application ports.

All PK-only lookups additionally verify `tenant_id` against the value bound
via `bind_tenant_to_session` — defense in depth on top of the auto-filter
installed by `qzdap_persistence.tenant_guard.install_tenant_loader`.
"""

from __future__ import annotations

from uuid import UUID

from qzdap_persistence.tenant_guard import current_tenant_id
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from qzdap.modules.identity.adapter.http.mappers import (
    api_key_orm_to_domain,
    tenant_orm_to_domain,
    user_orm_to_domain,
    workspace_orm_to_domain,
)
from qzdap.modules.identity.adapter.persistence.models import (
    APIKeyORM,
    TenantORM,
    UserORM,
    WorkspaceORM,
)
from qzdap.modules.identity.application.ports import (
    APIKeyRepository,
    TenantRepository,
    UserRepository,
    WorkspaceRepository,
)
from qzdap.modules.identity.domain import APIKey, Tenant, User, Workspace


def _cross_tenant(o: object) -> bool:
    """Return True if the loaded ORM row's tenant_id doesn't match the
    session-bound tenant. Used to silently None-out PK-only lookups that
    would otherwise leak cross-tenant rows before the route-level check."""
    bound = current_tenant_id()
    if bound is None:
        return False
    return getattr(o, "tenant_id", None) != bound


class SqlTenantRepository(TenantRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def add(self, tenant: Tenant) -> None:
        # On the tenants table itself, `tenant_id` is the tenant's own id
        # (tenants are the root of the tenant hierarchy).
        self._s.add(
            TenantORM(
                id=tenant.id,
                tenant_id=tenant.id,
                slug=tenant.slug,
                display_name=tenant.display_name,
                status=tenant.status.value,
                created_at=tenant.created_at,
                metadata=tenant.metadata,
            )
        )

    async def get(self, tenant_id: UUID) -> Tenant | None:
        bound = current_tenant_id()
        if bound is not None and bound != tenant_id:
            return None
        o = await self._s.get(TenantORM, tenant_id)
        return tenant_orm_to_domain(o) if o else None

    async def get_by_slug(self, slug: str) -> Tenant | None:
        q = select(TenantORM).where(TenantORM.slug == slug)
        o = (await self._s.execute(q)).scalar_one_or_none()
        return tenant_orm_to_domain(o) if o else None


class SqlWorkspaceRepository(WorkspaceRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def add(self, workspace: Workspace) -> None:
        self._s.add(
            WorkspaceORM(
                id=workspace.id,
                tenant_id=workspace.tenant_id,
                slug=workspace.slug,
                display_name=workspace.display_name,
                status=workspace.status.value,
                created_at=workspace.created_at,
                metadata=workspace.metadata,
            )
        )

    async def get(self, workspace_id: UUID) -> Workspace | None:
        o = await self._s.get(WorkspaceORM, workspace_id)
        if o is None or _cross_tenant(o):
            return None
        return workspace_orm_to_domain(o)

    async def list_for_tenant(
        self, tenant_id: UUID, limit: int, offset: int
    ) -> list[Workspace]:
        q = (
            select(WorkspaceORM)
            .where(WorkspaceORM.tenant_id == tenant_id)
            .order_by(WorkspaceORM.created_at)
            .limit(limit)
            .offset(offset)
        )
        rows = (await self._s.execute(q)).scalars().all()
        return [workspace_orm_to_domain(o) for o in rows]

    async def count_for_tenant(self, tenant_id: UUID) -> int:
        q = (
            select(func.count())
            .select_from(WorkspaceORM)
            .where(WorkspaceORM.tenant_id == tenant_id)
        )
        return int((await self._s.execute(q)).scalar_one())


class SqlUserRepository(UserRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def add(self, user: User) -> None:
        self._s.add(
            UserORM(
                id=user.id,
                tenant_id=user.tenant_id,
                email=user.email,
                display_name=user.display_name,
                status=user.status.value,
                created_at=user.created_at,
                hashed_password=user.hashed_password,
                metadata=user.metadata,
            )
        )

    async def get(self, user_id: UUID) -> User | None:
        o = await self._s.get(UserORM, user_id)
        if o is None or _cross_tenant(o):
            return None
        return user_orm_to_domain(o)

    async def get_by_email(self, tenant_id: UUID, email: str) -> User | None:
        q = select(UserORM).where(
            UserORM.tenant_id == tenant_id, UserORM.email == email.lower()
        )
        o = (await self._s.execute(q)).scalar_one_or_none()
        return user_orm_to_domain(o) if o else None

    async def get_by_email_global(self, email: str) -> User | None:
        # Login flow: caller does not know the tenant_id ahead of time. Email
        # is assumed globally unique — a precondition enforced upstream by the
        # registration flow. Returns the first match if multiple exist (TODO:
        # harden once a global uniqueness constraint lands on users.email).
        q = (
            select(UserORM)
            .where(UserORM.email == email.lower())
            .order_by(UserORM.created_at)
            .limit(1)
        )
        o = (await self._s.execute(q)).scalar_one_or_none()
        return user_orm_to_domain(o) if o else None


class SqlAPIKeyRepository(APIKeyRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def add(self, api_key: APIKey) -> None:
        self._s.add(
            APIKeyORM(
                id=api_key.id,
                tenant_id=api_key.tenant_id,
                workspace_id=api_key.workspace_id,
                owner_user_id=api_key.owner_user_id,
                name=api_key.name,
                prefix=api_key.prefix,
                hashed_secret=api_key.hashed_secret,
                status=api_key.status.value,
                created_at=api_key.created_at,
                expires_at=api_key.expires_at,
                last_used_at=api_key.last_used_at,
            )
        )

    async def get(self, api_key_id: UUID) -> APIKey | None:
        o = await self._s.get(APIKeyORM, api_key_id)
        if o is None or _cross_tenant(o):
            return None
        return api_key_orm_to_domain(o)

    async def list_for_owner(self, user_id: UUID) -> list[APIKey]:
        q = (
            select(APIKeyORM)
            .where(APIKeyORM.owner_user_id == user_id)
            .order_by(APIKeyORM.created_at.desc())
        )
        rows = (await self._s.execute(q)).scalars().all()
        bound = current_tenant_id()
        return [
            api_key_orm_to_domain(o)
            for o in rows
            if bound is None or o.tenant_id == bound
        ]

    async def update(self, api_key: APIKey) -> None:
        # Existing-row update path used by revoke.
        o = await self._s.get(APIKeyORM, api_key.id)
        if o is None:
            if _cross_tenant(api_key):  # type: ignore[arg-type]
                return
            self._s.add(
                APIKeyORM(
                    id=api_key.id,
                    tenant_id=api_key.tenant_id,
                    workspace_id=api_key.workspace_id,
                    owner_user_id=api_key.owner_user_id,
                    name=api_key.name,
                    prefix=api_key.prefix,
                    hashed_secret=api_key.hashed_secret,
                    status=api_key.status.value,
                    created_at=api_key.created_at,
                    expires_at=api_key.expires_at,
                    last_used_at=api_key.last_used_at,
                )
            )
            return
        if _cross_tenant(o):
            return
        o.status = api_key.status.value
        o.expires_at = api_key.expires_at
        o.last_used_at = api_key.last_used_at
