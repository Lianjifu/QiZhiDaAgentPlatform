from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Protocol, runtime_checkable
from uuid import UUID

from qzdap.modules.memory.domain.entities import (
    L1Session,
    L2Fact,
    L3Entry,
    PromotionEvent,
    RetentionPolicy,
)


@runtime_checkable
class EmbeddingPort(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...


@dataclass(slots=True, frozen=True)
class VectorHit:
    item_id: UUID
    score: float
    layer: str
    content: str


@runtime_checkable
class VectorSearchPort(Protocol):
    async def upsert(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        item_id: UUID,
        layer: str,
        content: str,
        embedding: list[float],
    ) -> None: ...

    async def delete(self, ids: list[UUID]) -> None: ...

    async def search(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        query_embedding: list[float],
        top_k: int,
    ) -> list[VectorHit]: ...


class MemoryCatalogRepository(ABC):
    @abstractmethod
    async def add_l1(self, item: L1Session) -> None: ...

    @abstractmethod
    async def get_l1(self, item_id: UUID) -> L1Session | None: ...

    @abstractmethod
    async def list_l1(self, workspace_id: UUID) -> list[L1Session]: ...

    @abstractmethod
    async def update_l1(self, item: L1Session) -> None: ...

    @abstractmethod
    async def add_l2(self, item: L2Fact) -> None: ...

    @abstractmethod
    async def get_l2(self, item_id: UUID) -> L2Fact | None: ...

    @abstractmethod
    async def list_l2(self, workspace_id: UUID) -> list[L2Fact]: ...

    @abstractmethod
    async def update_l2(self, item: L2Fact) -> None: ...

    @abstractmethod
    async def add_l3(self, item: L3Entry) -> None: ...

    @abstractmethod
    async def get_l3(self, item_id: UUID) -> L3Entry | None: ...

    @abstractmethod
    async def list_l3(self, workspace_id: UUID) -> list[L3Entry]: ...

    @abstractmethod
    async def add_promotion(self, item: PromotionEvent) -> None: ...

    @abstractmethod
    async def list_promotions(self, workspace_id: UUID) -> list[PromotionEvent]: ...

    @abstractmethod
    async def add_policy(self, item: RetentionPolicy) -> None: ...

    @abstractmethod
    async def list_policies(self, workspace_id: UUID) -> list[RetentionPolicy]: ...

    @abstractmethod
    async def get_policy_by_label(self, workspace_id: UUID, label: str) -> RetentionPolicy | None: ...


__all__ = [
    "EmbeddingPort",
    "MemoryCatalogRepository",
    "VectorHit",
    "VectorSearchPort",
]
