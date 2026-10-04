"""Identity domain events. Past-tense naming convention."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from qzdap_kernel.events import DomainEvent


@dataclass(slots=True, frozen=True)
class TenantCreated(DomainEvent):
    tenant_id: UUID
    slug: str

    def _as_payload_dict(self) -> dict[str, Any]:
        return {"tenant_id": str(self.tenant_id), "slug": self.slug}


@dataclass(slots=True, frozen=True)
class WorkspaceCreated(DomainEvent):
    workspace_id: UUID
    tenant_id: UUID
    slug: str

    def _as_payload_dict(self) -> dict[str, Any]:
        return {
            "workspace_id": str(self.workspace_id),
            "tenant_id": str(self.tenant_id),
            "slug": self.slug,
        }


@dataclass(slots=True, frozen=True)
class UserRegistered(DomainEvent):
    user_id: UUID
    tenant_id: UUID
    email: str

    def _as_payload_dict(self) -> dict[str, Any]:
        return {
            "user_id": str(self.user_id),
            "tenant_id": str(self.tenant_id),
            "email": self.email,
        }


@dataclass(slots=True, frozen=True)
class APIKeyIssued(DomainEvent):
    api_key_id: UUID
    tenant_id: UUID
    workspace_id: UUID | None
    owner_user_id: UUID

    def _as_payload_dict(self) -> dict[str, Any]:
        return {
            "api_key_id": str(self.api_key_id),
            "tenant_id": str(self.tenant_id),
            "workspace_id": str(self.workspace_id) if self.workspace_id else None,
            "owner_user_id": str(self.owner_user_id),
        }


@dataclass(slots=True, frozen=True)
class APIKeyRevoked(DomainEvent):
    api_key_id: UUID
    tenant_id: UUID

    def _as_payload_dict(self) -> dict[str, Any]:
        return {
            "api_key_id": str(self.api_key_id),
            "tenant_id": str(self.tenant_id),
        }
