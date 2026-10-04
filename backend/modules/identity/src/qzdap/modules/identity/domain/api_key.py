"""APIKey aggregate.

An APIKey is a bearer credential for service-to-service auth. It carries a
prefix (visible in logs) and an argon2-hashed secret; only the raw value is
shown to the caller once at creation time.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Self
from uuid import UUID

from qzdap.modules.identity.domain.events import APIKeyIssued, APIKeyRevoked


class APIKeyStatus(StrEnum):
    ACTIVE = "active"
    REVOKED = "revoked"


@dataclass(slots=True, frozen=True)
class APIKey:
    id: UUID
    tenant_id: UUID
    workspace_id: UUID | None
    owner_user_id: UUID
    name: str
    prefix: str
    hashed_secret: str
    status: APIKeyStatus
    created_at: datetime
    expires_at: datetime | None = None
    last_used_at: datetime | None = None

    @classmethod
    def issue(
        cls,
        *,
        id: UUID,
        tenant_id: UUID,
        workspace_id: UUID | None,
        owner_user_id: UUID,
        name: str,
        hashed_secret: str,
        raw_secret: str,
        ttl_days: int | None = None,
    ) -> tuple[Self, str]:
        """Create a new APIKey. Returns (key, raw_secret)."""
        prefix = raw_secret[:8]
        now = datetime.now(UTC)
        expires = now + timedelta(days=ttl_days) if ttl_days else None
        key = cls(
            id=id,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            owner_user_id=owner_user_id,
            name=name.strip() or "default",
            prefix=prefix,
            hashed_secret=hashed_secret,
            status=APIKeyStatus.ACTIVE,
            created_at=now,
            expires_at=expires,
        )
        return key, raw_secret

    def raise_issued_event(self) -> APIKeyIssued:
        return APIKeyIssued(
            api_key_id=self.id,
            tenant_id=self.tenant_id,
            workspace_id=self.workspace_id,
            owner_user_id=self.owner_user_id,
        )

    def revoke(self) -> Self:
        return type(self)(
            id=self.id,
            tenant_id=self.tenant_id,
            workspace_id=self.workspace_id,
            owner_user_id=self.owner_user_id,
            name=self.name,
            prefix=self.prefix,
            hashed_secret=self.hashed_secret,
            status=APIKeyStatus.REVOKED,
            created_at=self.created_at,
            expires_at=self.expires_at,
            last_used_at=self.last_used_at,
        )

    def raise_revoked_event(self) -> APIKeyRevoked:
        return APIKeyRevoked(
            api_key_id=self.id,
            tenant_id=self.tenant_id,
        )

    @staticmethod
    def generate_secret() -> str:
        """Generate a 32-byte URL-safe secret. Prefix carries the first 8 chars."""
        return secrets.token_urlsafe(32)
