"""User aggregate.

A User belongs to one or more workspaces via `UserWorkspace` (join entity).
A User always belongs to exactly one tenant.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Self
from uuid import UUID

from qzdap.modules.identity.domain.events import UserRegistered

_EMAIL_RE = __import__("re").compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class UserStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    DELETED = "deleted"


@dataclass(slots=True, frozen=True)
class User:
    id: UUID
    tenant_id: UUID
    email: str
    display_name: str
    status: UserStatus
    created_at: datetime
    hashed_password: str | None = None
    metadata: dict = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        *,
        id: UUID,
        tenant_id: UUID,
        email: str,
        display_name: str,
        hashed_password: str | None = None,
    ) -> Self:
        if not _EMAIL_RE.match(email):
            raise ValueError(f"invalid email: {email!r}")
        return cls(
            id=id,
            tenant_id=tenant_id,
            email=email.lower().strip(),
            display_name=display_name.strip() or email.split("@")[0],
            status=UserStatus.ACTIVE,
            created_at=datetime.now(UTC),
            hashed_password=hashed_password,
        )

    def raise_registered_event(self) -> UserRegistered:
        return UserRegistered(
            user_id=self.id,
            tenant_id=self.tenant_id,
            email=self.email,
        )
