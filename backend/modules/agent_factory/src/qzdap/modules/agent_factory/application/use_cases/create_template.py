"""CreateAgentTemplateUseCase.

Persists a new :class:`AgentTemplate` after enforcing name uniqueness
inside the tenant.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from qzdap_schema.ids import TenantId, UserId, WorkspaceId

from qzdap.modules.agent_factory.application.ports import (
    AgentFactoryEventPublisher,
    AgentTemplateRepository,
)
from qzdap.modules.agent_factory.domain.entities import AgentTemplate
from qzdap.modules.agent_factory.domain.events import AgentTemplateCreated

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class CreateAgentTemplateUseCase:
    repository: AgentTemplateRepository
    publisher: AgentFactoryEventPublisher | None = None
    policy_guard: object | None = None

    async def execute(
        self,
        *,
        tenant_id: TenantId,
        workspace_id: WorkspaceId,
        name: str,
        description: str,
        default_model_id: str,
        default_system_prompt: str,
        metadata: dict[str, Any] | None = None,
        created_by: UserId | None = None,
    ) -> AgentTemplate:
        # Policy gate (optional, dev shell can disable).
        if self.policy_guard is not None:
            from qzdap_vault.actor import ActorContext

            await self.policy_guard.check(  # type: ignore[attr-defined]
                actor=ActorContext(
                    tenant_id=tenant_id,
                    workspace_id=workspace_id,
                    principal_id=created_by,
                ),
                action="agent_factory:template:create",
                resource={"workspace_id": str(workspace_id)},
            )

        # Name uniqueness inside tenant.
        existing = await self.repository.get_by_name(tenant_id=tenant_id, name=name)
        if existing is not None:
            from qzdap.modules.agent_factory.domain.errors import (
                AgentTemplateNameConflict,
            )

            raise AgentTemplateNameConflict(
                f"agent template name {name!r} already exists in tenant"
            )

        template = AgentTemplate.create(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            name=name,
            description=description,
            default_model_id=default_model_id,
            default_system_prompt=default_system_prompt,
            metadata=metadata,
            created_by=created_by or UserId(uuid4()),
        )
        saved = await self.repository.add(template)

        if self.publisher is not None:
            try:
                await self.publisher.publish(
                    AgentTemplateCreated(
                        template_id=saved.id,
                        tenant_id=saved.tenant_id,
                        workspace_id=saved.workspace_id,
                        name=saved.name,
                        created_by=saved.created_by,
                    )
                )
            except Exception:  # pragma: no cover - defensive
                logger.exception("publish AgentTemplateCreated failed for %s", saved.id)

        return saved


__all__ = ["CreateAgentTemplateUseCase"]
