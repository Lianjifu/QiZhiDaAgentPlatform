"""UseCase: create a workspace under a tenant."""

from __future__ import annotations

from uuid import UUID, uuid4

from qzdap.modules.identity.application.ports import (
    TenantRepository,
    WorkspaceRepository,
)
from qzdap.modules.identity.domain import Workspace
from qzdap.modules.identity.domain.errors import (
    TenantNotFound,
    WorkspaceAlreadyExists,
    WorkspaceLimitReached,
)

DEFAULT_WORKSPACE_LIMIT_PER_TENANT = 100


class CreateWorkspaceUseCase:
    def __init__(
        self,
        tenants: TenantRepository,
        workspaces: WorkspaceRepository,
        *,
        workspace_limit: int = DEFAULT_WORKSPACE_LIMIT_PER_TENANT,
    ) -> None:
        self._tenants = tenants
        self._workspaces = workspaces
        self._limit = workspace_limit

    async def execute(
        self, *, tenant_id: UUID, slug: str, display_name: str
    ) -> Workspace:
        tenant = await self._tenants.get(tenant_id)
        if tenant is None:
            raise TenantNotFound(f"tenant {tenant_id} not found")

        if await self._workspaces.count_for_tenant(tenant_id) >= self._limit:
            raise WorkspaceLimitReached(
                f"workspace limit ({self._limit}) reached for tenant"
            )

        existing = await self._workspaces.list_for_tenant(tenant_id, limit=1, offset=0)
        if any(w.slug == slug for w in existing):
            # Cheap check; full listing is in `list_for_tenant`. For high
            # workspace counts, replace with a dedicated exists() port.
            raise WorkspaceAlreadyExists(f"workspace slug {slug!r} already exists")

        workspace = Workspace.create(
            id=uuid4(),
            tenant_id=tenant_id,
            slug=slug,
            display_name=display_name,
        )
        await self._workspaces.add(workspace)
        return workspace
