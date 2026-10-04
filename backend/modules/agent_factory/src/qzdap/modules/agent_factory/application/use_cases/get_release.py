"""GetReleaseUseCase + ListReleasesUseCase — read-only views on releases."""

from __future__ import annotations

from dataclasses import dataclass

from qzdap_schema.ids import AgentTemplateId, ReleaseId, TenantId

from qzdap.modules.agent_factory.application.ports import ReleaseRepository
from qzdap.modules.agent_factory.domain.entities import Release


@dataclass(slots=True)
class GetReleaseUseCase:
    repository: ReleaseRepository

    async def execute(self, *, tenant_id: TenantId, release_id: ReleaseId) -> Release:
        rel = await self.repository.get(tenant_id=tenant_id, release_id=release_id)
        if rel is None:
            from qzdap.modules.agent_factory.domain.errors import ReleaseNotFound

            raise ReleaseNotFound(f"release {release_id} not found in tenant")
        return rel


@dataclass(slots=True)
class ListReleasesUseCase:
    repository: ReleaseRepository

    async def execute(
        self,
        *,
        tenant_id: TenantId,
        template_id: AgentTemplateId,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Release]:
        return await self.repository.list_for_template(
            tenant_id=tenant_id,
            template_id=template_id,
            limit=limit,
            offset=offset,
        )


__all__ = ["GetReleaseUseCase", "ListReleasesUseCase"]
