"""Adapter wiring the memory catalog into agent_runtime's MemoryPort."""

from __future__ import annotations

from uuid import UUID

from qzdap.modules.memory.application.services import MemoryService


class MemoryServiceAdapter:
    """Adapts ``MemoryService.recall`` → ``MemoryPort.recall``."""

    def __init__(self, memory_service: MemoryService) -> None:
        self._service = memory_service

    async def recall(
        self, *, tenant_id: UUID, workspace_id: UUID, query: str, top_k: int
    ) -> list[dict]:
        return await self._service.recall(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            query=query,
            top_k=top_k,
        )

    async def write(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        owner_id: UUID,
        content: str,
        metadata: dict | None = None,
    ) -> dict:
        return await self._service.write(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            owner_id=owner_id,
            content=content,
            metadata=metadata,
        )


__all__ = ["MemoryServiceAdapter"]
