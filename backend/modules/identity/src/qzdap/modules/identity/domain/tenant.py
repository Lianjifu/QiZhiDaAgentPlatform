"""Tenant aggregate.

A Tenant is the top-level boundary. Every other entity is either inside a
tenant or cross-tenant (and then it must be system-owned).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Self
from uuid import UUID

from qzdap.modules.identity.domain.events import TenantCreated

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,38}[a-z0-9]$")


class TenantStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    ARCHIVED = "archived"


@dataclass(slots=True, frozen=True)
class Tenant:
    id: UUID
    slug: str
    display_name: str
    status: TenantStatus
    created_at: datetime
    metadata: dict = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        *,
        id: UUID,
        slug: str,
        display_name: str,
        metadata: dict | None = None,
    ) -> Self:
        if not _SLUG_RE.match(slug):
            raise ValueError(
                f"invalid tenant slug: {slug!r} (must be 3-40 lowercase alphanumeric + dashes)"
            )
        return cls(
            id=id,
            slug=slug,
            display_name=display_name.strip() or slug,
            status=TenantStatus.ACTIVE,
            created_at=datetime.now(UTC),
            metadata=dict(metadata or {}),
        )

    def raise_created_event(self) -> TenantCreated:
        return TenantCreated(tenant_id=self.id, slug=self.slug)

    def suspend(self) -> Self:
        return type(self)(
            id=self.id,
            slug=self.slug,
            display_name=self.display_name,
            status=TenantStatus.SUSPENDED,
            created_at=self.created_at,
            metadata=dict(self.metadata),
        )
