"""Mappers between domain ↔ ORM ↔ DTO. Pure functions."""

from __future__ import annotations

from uuid import UUID

from qzdap.modules.identity.adapter.http.dto import (
    APIKeyResponse,
    TenantResponse,
    UserResponse,
    WorkspaceResponse,
)
from qzdap.modules.identity.adapter.persistence.models import (
    APIKeyORM,
    TenantORM,
    UserORM,
    WorkspaceORM,
)
from qzdap.modules.identity.domain import APIKey, Tenant, User, Workspace
from qzdap.modules.identity.domain.tenant import TenantStatus
from qzdap.modules.identity.domain.user import UserStatus
from qzdap.modules.identity.domain.workspace import WorkspaceStatus


def tenant_orm_to_domain(o: TenantORM) -> Tenant:
    return Tenant(
        id=o.id,
        slug=o.slug,
        display_name=o.display_name,
        status=TenantStatus(o.status),
        created_at=o.created_at,
        metadata=dict(o.metadata_ or {}),
    )


def tenant_domain_to_response(t: Tenant) -> TenantResponse:
    return TenantResponse(
        id=t.id,
        slug=t.slug,
        display_name=t.display_name,
        status=t.status.value,
        created_at=t.created_at,
        metadata=dict(t.metadata or {}),
    )


def workspace_orm_to_domain(o: WorkspaceORM) -> Workspace:
    return Workspace(
        id=o.id,
        tenant_id=o.tenant_id,
        slug=o.slug,
        display_name=o.display_name,
        status=WorkspaceStatus(o.status),
        created_at=o.created_at,
        metadata=dict(o.metadata_ or {}),
    )


def workspace_domain_to_response(w: Workspace) -> WorkspaceResponse:
    return WorkspaceResponse(
        id=w.id,
        tenant_id=w.tenant_id,
        slug=w.slug,
        display_name=w.display_name,
        status=w.status.value,
        created_at=w.created_at,
        metadata=dict(w.metadata or {}),
    )


def user_orm_to_domain(o: UserORM) -> User:
    return User(
        id=o.id,
        tenant_id=o.tenant_id,
        email=o.email,
        display_name=o.display_name,
        status=UserStatus(o.status),
        created_at=o.created_at,
        hashed_password=o.hashed_password,
        metadata=dict(o.metadata_ or {}),
    )


def user_domain_to_response(
    u: User, *, workspace_id: UUID | None = None
) -> UserResponse:
    return UserResponse(
        id=u.id,
        tenant_id=u.tenant_id,
        email=u.email,
        display_name=u.display_name,
        status=u.status.value,
        created_at=u.created_at,
        workspace_id=workspace_id,
    )


def api_key_orm_to_domain(o: APIKeyORM) -> APIKey:
    from qzdap.modules.identity.domain.api_key import APIKeyStatus

    return APIKey(
        id=o.id,
        tenant_id=o.tenant_id,
        workspace_id=o.workspace_id,
        owner_user_id=o.owner_user_id,
        name=o.name,
        prefix=o.prefix,
        hashed_secret=o.hashed_secret,
        status=APIKeyStatus(o.status),
        created_at=o.created_at,
        expires_at=o.expires_at,
        last_used_at=o.last_used_at,
    )


def api_key_domain_to_response(k: APIKey, *, raw: str | None = None) -> APIKeyResponse:
    return APIKeyResponse(
        id=k.id,
        tenant_id=k.tenant_id,
        workspace_id=k.workspace_id,
        owner_user_id=k.owner_user_id,
        name=k.name,
        prefix=k.prefix,
        status=k.status.value,
        created_at=k.created_at,
        expires_at=k.expires_at,
        raw_secret=raw,
    )
