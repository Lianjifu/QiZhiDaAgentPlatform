"""UpdateAgentTemplateUseCase — flip status (active ↔ archived).

Only the status is mutable; the rest of the template is frozen at
creation.  To change prompt / model, create a new :class:`AgentVersion`.
"""

from __future__ import annotations

from dataclasses import dataclass

from qzdap_schema.ids import AgentTemplateId, TenantId

from qzdap.modules.agent_factory.application.ports import (
    AgentFactoryEventPublisher,
    AgentTemplateRepository,
)
from qzdap.modules.agent_factory.domain.entities import AgentTemplate
from qzdap.modules.agent_factory.domain.value_objects import AgentTemplateStatus


@dataclass(slots=True)
class UpdateAgentTemplateUseCase:
    repository: AgentTemplateRepository
    publisher: AgentFactoryEventPublisher | None = None
    policy_guard: object | None = None

    async def execute(
        self,
        *,
        tenant_id: TenantId,
        template_id: AgentTemplateId,
        status: AgentTemplateStatus,
    ) -> AgentTemplate:
        tpl = await self.repository.get(tenant_id=tenant_id, template_id=template_id)
        if tpl is None:
            from qzdap.modules.agent_factory.domain.errors import (
                AgentTemplateNotFound,
            )

            raise AgentTemplateNotFound(
                f"agent template {template_id} not found in tenant"
            )
        updated = tpl.with_status(status)
        return await self.repository.update(updated)


__all__ = ["UpdateAgentTemplateUseCase"]
