"""CreateAgentVersionUseCase — creates a draft version for an existing template."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from qzdap_schema.ids import (
    AgentTemplateId,
    AgentVersionId,
    TenantId,
    UserId,
    WorkspaceId,
)

from qzdap.modules.agent_factory.application.ports import (
    AgentFactoryEventPublisher,
    AgentTemplateRepository,
    AgentVersionRepository,
)
from qzdap.modules.agent_factory.domain.entities import AgentVersion

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class CreateAgentVersionUseCase:
    template_repository: AgentTemplateRepository
    version_repository: AgentVersionRepository
    publisher: AgentFactoryEventPublisher | None = None
    policy_guard: object | None = None

    async def execute(
        self,
        *,
        tenant_id: TenantId,
        workspace_id: WorkspaceId,
        template_id: AgentTemplateId,
        version_tag: str,
        system_prompt: str | None = None,
        model_id: str | None = None,
        allowed_tools: tuple[str, ...] = (),
        allowed_skills: tuple[str, ...] = (),
        knowledge_package_ids: tuple[str, ...] = (),
        plan_dsl_snapshot: dict[str, Any] | None = None,
        max_total_steps: int | None = None,
        release_notes: str = "",
        metadata: dict[str, Any] | None = None,
        created_by: UserId | None = None,
        version_id: AgentVersionId | None = None,
    ) -> AgentVersion:
        # policy gate
        if self.policy_guard is not None:
            from qzdap_vault.actor import ActorContext

            await self.policy_guard.check(  # type: ignore[attr-defined]
                actor=ActorContext(
                    tenant_id=tenant_id,
                    workspace_id=workspace_id,
                    principal_id=created_by,
                ),
                action="agent_factory:version:create",
                resource={"template_id": str(template_id)},
            )

        # resolve template (inherits defaults)
        template = await self.template_repository.get(
            tenant_id=tenant_id, template_id=template_id
        )
        if template is None:
            from qzdap.modules.agent_factory.domain.errors import (
                AgentTemplateNotFound,
            )

            raise AgentTemplateNotFound(
                f"agent template {template_id} not found in tenant"
            )

        # version_tag uniqueness per (tenant, template)
        existing = await self.version_repository.get_by_tag(
            tenant_id=tenant_id,
            template_id=template_id,
            version_tag=version_tag,
        )
        if existing is not None:
            from qzdap.modules.agent_factory.domain.errors import (
                AgentVersionTagConflict,
            )

            raise AgentVersionTagConflict(
                f"version_tag {version_tag!r} already exists for template"
            )

        version = AgentVersion.create_draft(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            template_id=template_id,
            version_tag=version_tag,
            system_prompt=system_prompt or template.default_system_prompt,
            model_id=model_id or template.default_model_id,
            allowed_tools=allowed_tools,
            allowed_skills=allowed_skills,
            knowledge_package_ids=knowledge_package_ids,
            plan_dsl_snapshot=plan_dsl_snapshot,
            max_total_steps=max_total_steps,
            release_notes=release_notes,
            metadata=metadata,
            created_by=created_by or UserId(uuid4()),
            version_id=version_id,
        )
        saved = await self.version_repository.add(version)
        return saved


__all__ = ["CreateAgentVersionUseCase"]
