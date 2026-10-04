"""Workspace aggregate.

Workspaces are sub-units of tenants. Each workspace owns users + resources;
cross-workspace access is forbidden unless explicitly granted.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Self
from uuid import UUID

from qzdap.modules.identity.domain.events import WorkspaceCreated


class WorkspaceStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


@dataclass(slots=True, frozen=True)
class Workspace:
    id: UUID
    tenant_id: UUID
    slug: str
    display_name: str
    status: WorkspaceStatus
    created_at: datetime
    metadata: dict = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        *,
        id: UUID,
        tenant_id: UUID,
        slug: str,
        display_name: str,
    ) -> Self:
        if not slug or not slug.replace("-", "").replace("_", "").isalnum():
            raise ValueError(f"invalid workspace slug: {slug!r}")
        return cls(
            id=id,
            tenant_id=tenant_id,
            slug=slug.lower(),
            display_name=display_name.strip() or slug,
            status=WorkspaceStatus.ACTIVE,
            created_at=datetime.now(UTC),
            metadata={},
        )

    def raise_created_event(self) -> WorkspaceCreated:
        return WorkspaceCreated(
            workspace_id=self.id,
            tenant_id=self.tenant_id,
            slug=self.slug,
        )
