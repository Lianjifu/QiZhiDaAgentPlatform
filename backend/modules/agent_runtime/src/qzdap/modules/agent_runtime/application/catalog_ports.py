from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from qzdap.modules.agent_runtime.domain.catalog import CatalogAgent


class CatalogAgentRepository(ABC):
    @abstractmethod
    async def add(self, agent: CatalogAgent) -> None: ...

    @abstractmethod
    async def get(self, agent_id: UUID) -> CatalogAgent | None: ...

    @abstractmethod
    async def list_for_workspace(self, workspace_id: UUID) -> list[CatalogAgent]: ...

    @abstractmethod
    async def update(self, agent: CatalogAgent) -> None: ...

    @abstractmethod
    async def delete(self, agent_id: UUID) -> None: ...


class CatalogAgentUserStateRepository(ABC):
    @abstractmethod
    async def set_favorite(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        user_id: UUID,
        agent_id: UUID,
        on: bool,
    ) -> None: ...


__all__ = ["CatalogAgentRepository", "CatalogAgentUserStateRepository"]
