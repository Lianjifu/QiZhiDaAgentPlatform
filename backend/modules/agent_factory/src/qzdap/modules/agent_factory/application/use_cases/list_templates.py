"""ListAgentTemplatesUseCase — paginated list of templates in a workspace."""

from __future__ import annotations

from dataclasses import dataclass

from qzdap.modules.agent_factory.application.ports import AgentTemplateRepository
from qzdap.modules.agent_factory.domain.entities import AgentTemplate
from qzdap_kernel.ids import TenantId, WorkspaceId


@dataclass(slots=True)
class ListAgentTemplatesUseCase:
    repository: AgentTemplateRepository

    async def execute(
        self,
        *,
        tenant_id: TenantId,
        workspace_id: WorkspaceId,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AgentTemplate]:
        return await self.repository.list(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            limit=limit,
            offset=offset,
        )


__all__ = ["ListAgentTemplatesUseCase"]
