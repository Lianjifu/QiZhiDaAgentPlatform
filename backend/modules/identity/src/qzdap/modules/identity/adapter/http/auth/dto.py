"""DTOs for the auth (login) subpackage.

Login contract: cross-tenant password auth that returns the access token +
the resolved user in one round-trip (replaces the prior 422-prone
``tenant_id`` requirement and the follow-up ``GET /users/me``).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, EmailStr, Field

from qzdap.modules.identity.adapter.http.dto import UserResponse


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class LoginResponse(BaseModel):
    access_token: str
    token_type: Literal["Bearer"] = "Bearer"
    expires_at: int
    user: UserResponse