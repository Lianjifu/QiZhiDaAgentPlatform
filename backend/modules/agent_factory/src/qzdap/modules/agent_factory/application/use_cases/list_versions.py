"""ListAgentVersionsUseCase — paginated list of versions for a template."""

from __future__ import annotations

from dataclasses import dataclass

from qzdap_schema.ids import AgentTemplateId, TenantId

from qzdap.modules.agent_factory.application.ports import AgentVersionRepository
from qzdap.modules.agent_factory.domain.entities import AgentVersion


@dataclass(slots=True)
class ListAgentVersionsUseCase:
    repository: AgentVersionRepository

    async def execute(
        self,
        *,
        tenant_id: TenantId,
        template_id: AgentTemplateId,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AgentVersion]:
        return await self.repository.list_for_template(
            tenant_id=tenant_id,
            template_id=template_id,
            limit=limit,
            offset=offset,
        )


__all__ = ["ListAgentVersionsUseCase"]
