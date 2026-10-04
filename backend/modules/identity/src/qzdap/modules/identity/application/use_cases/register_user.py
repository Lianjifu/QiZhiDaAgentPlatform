"""UseCase: register a user."""

from __future__ import annotations

from uuid import UUID, uuid4

from qzdap.modules.identity.application.ports import (
    Hasher,
    TenantRepository,
    UserRepository,
)
from qzdap.modules.identity.domain import User
from qzdap.modules.identity.domain.errors import (
    TenantNotFound,
    UserAlreadyExists,
)


class RegisterUserUseCase:
    def __init__(
        self,
        tenants: TenantRepository,
        users: UserRepository,
        hasher: Hasher,
    ) -> None:
        self._tenants = tenants
        self._users = users
        self._hasher = hasher

    async def execute(
        self,
        *,
        tenant_id: UUID,
        email: str,
        display_name: str,
        password: str | None = None,
    ) -> User:
        tenant = await self._tenants.get(tenant_id)
        if tenant is None:
            raise TenantNotFound(f"tenant {tenant_id} not found")

        if await self._users.get_by_email(tenant_id, email) is not None:
            raise UserAlreadyExists(f"email {email!r} already in use")

        hashed = self._hasher.hash(password) if password else None
        user = User.create(
            id=uuid4(),
            tenant_id=tenant_id,
            email=email,
            display_name=display_name,
            hashed_password=hashed,
        )
        await self._users.add(user)
        return user
