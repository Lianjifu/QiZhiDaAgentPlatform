"""UseCase: issue a new APIKey for a user."""

from __future__ import annotations

from uuid import UUID, uuid4

from qzdap.modules.identity.application.ports import (
    APIKeyRepository,
    Hasher,
    UserRepository,
)
from qzdap.modules.identity.domain import APIKey
from qzdap.modules.identity.domain.errors import UserNotFound


class IssueAPIKeyUseCase:
    def __init__(
        self,
        users: UserRepository,
        api_keys: APIKeyRepository,
        hasher: Hasher,
    ) -> None:
        self._users = users
        self._keys = api_keys
        self._hasher = hasher

    async def execute(
        self,
        *,
        owner_user_id: UUID,
        name: str,
        workspace_id: UUID | None = None,
        ttl_days: int | None = None,
    ) -> tuple[APIKey, str]:
        user = await self._users.get(owner_user_id)
        if user is None:
            raise UserNotFound(f"user {owner_user_id} not found")

        raw_secret = APIKey.generate_secret()
        hashed = self._hasher.hash(raw_secret)

        key, raw = APIKey.issue(
            id=uuid4(),
            tenant_id=user.tenant_id,
            workspace_id=workspace_id,
            owner_user_id=user.id,
            name=name,
            hashed_secret=hashed,
            raw_secret=raw_secret,
            ttl_days=ttl_days,
        )
        await self._keys.add(key)
        return key, raw


# Compatibility shim for backwards import
