"""UseCase: password-based login → access token + user payload.

Public surface (a single method, returning ``LoginResult`` so callers can
fold token + expires_at + user into one response without a second
``/users/me`` round-trip).
"""

from __future__ import annotations

from dataclasses import dataclass

from uuid import UUID

from qzdap.modules.identity.application.ports import (
    AccessTokenIssuer,
    Hasher,
    UserRepository,
    WorkspaceRepository,
)
from qzdap.modules.identity.domain import User
from qzdap.modules.identity.domain.errors import InvalidCredentials


@dataclass(slots=True, frozen=True)
class LoginResult:
    token: str
    expires_at: int
    user: User
    workspace_id: UUID | None = None


class LoginUseCase:
    def __init__(
        self,
        users: UserRepository,
        hasher: Hasher,
        issuer: AccessTokenIssuer,
        workspaces: WorkspaceRepository | None = None,
    ) -> None:
        self._users = users
        self._hasher = hasher
        self._issuer = issuer
        self._workspaces = workspaces

    async def execute(self, *, email: str, password: str) -> LoginResult:
        # Cross-tenant lookup: the caller (login form) does not know the
        # tenant_id ahead of time. Email is assumed globally unique — see
        # UserRepository.get_by_email_global docstring.
        user = await self._users.get_by_email_global(email)
        # Same error message for "no such user" and "wrong password" — do
        # not leak which side failed (anti-enumeration).
        if user is None or user.hashed_password is None:
            raise InvalidCredentials("invalid email or password")
        if not self._hasher.verify(password, user.hashed_password):
            raise InvalidCredentials("invalid email or password")
        workspace_id: UUID | None = None
        if self._workspaces is not None:
            found = await self._workspaces.list_for_tenant(user.tenant_id, limit=1, offset=0)
            workspace_id = found[0].id if found else None
        token, exp = self._issuer.issue(user, workspace_id)
        return LoginResult(
            token=token,
            expires_at=exp,
            user=user,
            workspace_id=workspace_id,
        )