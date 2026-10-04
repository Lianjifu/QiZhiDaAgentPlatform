"""HTTP DTOs for the identity module — wire-level shapes."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class CreateTenantRequest(BaseModel):
    slug: str = Field(
        min_length=3, max_length=40, pattern=r"^[a-z0-9][a-z0-9-]+[a-z0-9]$"
    )
    display_name: str = Field(min_length=1, max_length=120)
    metadata: dict = Field(default_factory=dict)


class TenantResponse(BaseModel):
    id: UUID
    slug: str
    display_name: str
    status: Literal["active", "suspended", "archived"]
    created_at: datetime
    metadata: dict


class CreateWorkspaceRequest(BaseModel):
    slug: str = Field(min_length=1, max_length=40, pattern=r"^[a-zA-Z0-9_-]+$")
    display_name: str = Field(min_length=1, max_length=120)


class WorkspaceResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    slug: str
    display_name: str
    status: Literal["active", "archived"]
    created_at: datetime
    metadata: dict


class RegisterUserRequest(BaseModel):
    email: EmailStr
    display_name: str = Field(min_length=1, max_length=120)
    password: str | None = Field(default=None, min_length=8, max_length=128)


class UserResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    email: str
    display_name: str
    status: Literal["active", "suspended", "deleted"]
    created_at: datetime
    workspace_id: UUID | None = None


class IssueAPIKeyRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    workspace_id: UUID | None = None
    ttl_days: int | None = Field(default=None, ge=1, le=3650)


class APIKeyResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    workspace_id: UUID | None
    owner_user_id: UUID
    name: str
    prefix: str
    status: Literal["active", "revoked"]
    created_at: datetime
    expires_at: datetime | None = None
    # The raw secret is ONLY included in the issue response; never on GET.
    raw_secret: str | None = None


# Login DTOs (LoginRequest / LoginResponse) live in
# ``adapter.http.auth.dto`` — see the auth/ subfolder for the password-auth
# contract.
