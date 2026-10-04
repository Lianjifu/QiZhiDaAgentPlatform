"""UseCase: revoke an API key (mark REVOKED, never delete)."""

from __future__ import annotations

from uuid import UUID

from qzdap.modules.identity.application.ports import APIKeyRepository
from qzdap.modules.identity.domain.errors import APIKeyNotFound, APIKeyRevoked


class RevokeAPIKeyUseCase:
    def __init__(self, api_keys: APIKeyRepository) -> None:
        self._keys = api_keys

    async def execute(self, *, api_key_id: UUID) -> None:
        key = await self._keys.get(api_key_id)
        if key is None:
            raise APIKeyNotFound(f"api key {api_key_id} not found")
        # Domain rule: revoking an already-revoked key is a no-op; we don't raise.
        # If you want strict semantics, raise APIKeyRevoked.
        _ = APIKeyRevoked
        if key.status.value == "revoked":
            return
        # Re-persist with revoked status — repos expose `update`.
        await self._keys.update(key.revoke())
