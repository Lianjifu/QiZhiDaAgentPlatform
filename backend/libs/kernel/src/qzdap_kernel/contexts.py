"""Tenant + Workspace context types.

The TenantWorkspaceContext is what gets attached to every request and threaded
through every UseCase. It guarantees we never accidentally cross tenants.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


@dataclass(slots=True, frozen=True)
class TenantContext:
    """A tenant scope. Anything you read/write must belong to this tenant."""

    tenant_id: UUID


@dataclass(slots=True, frozen=True)
class WorkspaceContext:
    """A workspace within a tenant. Workspace always implies its tenant."""

    tenant_id: UUID
    workspace_id: UUID


@dataclass(slots=True, frozen=True)
class TenantWorkspaceContext:
    """Union: tenant-wide OR a specific workspace.

    Use this when the operation may legitimately operate at tenant level
    (e.g. creating new workspaces, listing all workspaces) or at workspace
    level (most CRUD).
    """

    tenant_id: UUID
    workspace_id: UUID | None

    def to_workspace(self) -> WorkspaceContext:
        if self.workspace_id is None:
            raise ValueError("TenantWorkspaceContext is tenant-wide; no workspace")
        return WorkspaceContext(self.tenant_id, self.workspace_id)
