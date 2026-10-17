"""UpdateAgentVersionNotesUseCase — only allowed while the version is in DRAFT."""

from __future__ import annotations

from dataclasses import dataclass

from qzdap_schema.ids import AgentVersionId, TenantId

from qzdap.modules.agent_factory.application.ports import AgentVersionRepository
from qzdap.modules.agent_factory.domain.entities import AgentVersion


@dataclass(slots=True)
class UpdateAgentVersionNotesUseCase:
    repository: AgentVersionRepository

    async def execute(
        self,
        *,
        tenant_id: TenantId,
        version_id: AgentVersionId,
        release_notes: str,
    ) -> AgentVersion:
        version = await self.repository.get(tenant_id=tenant_id, version_id=version_id)
        if version is None:
            from qzdap.modules.agent_factory.domain.errors import (
                AgentVersionNotFound,
            )

            raise AgentVersionNotFound(
                f"agent version {version_id} not found in tenant"
            )
        # .with_release_notes raises AgentVersionImmutable if not draft.
        updated = version.with_release_notes(release_notes)
        saved = await self.repository.update(updated)
        # Phase 2: 显式 commit
        if hasattr(self.repository, "commit"):
            await self.repository.commit()  # type: ignore[attr-defined]
        return saved


__all__ = ["UpdateAgentVersionNotesUseCase"]
