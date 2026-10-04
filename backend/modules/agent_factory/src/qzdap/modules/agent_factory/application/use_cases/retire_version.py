"""RetireAgentVersionUseCase — RELEASED → RETIRED (immutable thereafter)."""

from __future__ import annotations

from dataclasses import dataclass

from qzdap_schema.ids import AgentVersionId, TenantId

from qzdap.modules.agent_factory.application.ports import AgentVersionRepository
from qzdap.modules.agent_factory.domain.entities import AgentVersion


@dataclass(slots=True)
class RetireAgentVersionUseCase:
    repository: AgentVersionRepository

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
        retired = version.retire()
        return await self.repository.update(retired)


__all__ = ["RetireAgentVersionUseCase"]
