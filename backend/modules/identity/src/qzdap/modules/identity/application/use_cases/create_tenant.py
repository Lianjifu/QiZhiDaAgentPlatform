"""UseCase: create a tenant.

Single-caller service. The composition root instantiates it with concrete
ports; nothing else touches the repos directly.
"""

from __future__ import annotations

from uuid import uuid4

from qzdap.modules.identity.application.ports import TenantRepository
from qzdap.modules.identity.domain import Tenant
from qzdap.modules.identity.domain.errors import TenantAlreadyExists


class CreateTenantUseCase:
    def __init__(self, tenants: TenantRepository) -> None:
        self._tenants = tenants

    async def execute(
        self, *, slug: str, display_name: str, metadata: dict | None = None
    ) -> Tenant:
        existing = await self._tenants.get_by_slug(slug)
        if existing is not None:
            raise TenantAlreadyExists(f"slug {slug!r} already taken")

        tenant = Tenant.create(
            id=uuid4(),
            slug=slug,
            display_name=display_name,
            metadata=metadata,
        )
        await self._tenants.add(tenant)
        return tenant
