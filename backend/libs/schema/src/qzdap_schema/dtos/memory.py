"""Memory entry DTO."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

MemoryScope = Literal["user", "agent", "workspace"]


class MemoryEntryDTO(BaseModel):
    id: UUID
    tenant_id: UUID
    workspace_id: UUID
    owner_id: UUID
    scope: MemoryScope
    content: dict
    metadata: dict = Field(default_factory=dict)
    revoked: bool = False
    created_at: datetime
    expires_at: datetime | None = None
