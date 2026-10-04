"""PublishAgentVersionUseCase — flip draft → published (immutable thereafter)."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from qzdap_schema.ids import AgentVersionId, TenantId

from qzdap.modules.agent_factory.application.ports import (
    AgentFactoryEventPublisher,
    AgentVersionRepository,
)
from qzdap.modules.agent_factory.domain.entities import AgentVersion

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class PublishAgentVersionUseCase:
    repository: AgentVersionRepository
    publisher: AgentFactoryEventPublisher | None = None
    policy_guard: object | None = None

    async def execute(
        self, *, tenant_id: TenantId, version_id: AgentVersionId
    ) -> AgentVersion:
        version = await self.repository.get(tenant_id=tenant_id, version_id=version_id)
        if version is None:
            from qzdap.modules.agent_factory.domain.errors import (
                AgentVersionNotFound,
            )

            raise AgentVersionNotFound(
                f"agent version {version_id} not found in tenant"
            )

        published = version.publish()
        saved = await self.repository.update(published)

        if self.publisher is not None:
            try:
                await self.publisher.publish(
                    __import__(
                        "qzdap.modules.agent_factory.domain.events",
                        fromlist=["AgentVersionPublished"],
                    ).AgentVersionPublished(
                        template_id=saved.template_id,
                        version_id=saved.id,
                        tenant_id=saved.tenant_id,
                        workspace_id=saved.workspace_id,
                        version_tag=saved.version_tag,
                    )
                )
            except Exception:  # pragma: no cover - defensive
                logger.exception(
                    "publish AgentVersionPublished failed for %s", saved.id
                )

        return saved


__all__ = ["PublishAgentVersionUseCase"]
