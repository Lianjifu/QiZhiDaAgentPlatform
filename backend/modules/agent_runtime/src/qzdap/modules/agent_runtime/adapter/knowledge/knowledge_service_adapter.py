"""Adapter wiring the knowledge catalog into agent_runtime's KnowledgePort."""

from __future__ import annotations

from uuid import UUID

from qzdap.modules.knowledge.application.services import KnowledgeService


class KnowledgeServiceAdapter:
    """Adapts ``KnowledgeService.search_query`` → ``KnowledgePort.search``."""

    def __init__(self, knowledge_service: KnowledgeService) -> None:
        self._service = knowledge_service

    async def search(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        query: str,
        top_k: int,
        package_ids: tuple[UUID, ...] = (),
    ) -> list[dict]:
        return await self._service.search_query(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            query=query,
            top_k=top_k,
            package_ids=tuple(str(item) for item in package_ids),
        )


__all__ = ["KnowledgeServiceAdapter"]
