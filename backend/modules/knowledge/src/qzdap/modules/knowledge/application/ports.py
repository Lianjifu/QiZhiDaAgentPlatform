from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Protocol, runtime_checkable
from uuid import UUID

from qzdap.modules.knowledge.domain.entities import (
    IndexedChunk,
    KnowledgeBase,
    KnowledgeDoc,
    KnowledgeEvalCase,
    KnowledgeSource,
    KnowledgeTask,
)


@runtime_checkable
class EmbeddingPort(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...


@dataclass(slots=True, frozen=True)
class VectorHit:
    chunk_id: UUID
    score: float
    kb_id: str
    doc_id: str
    ordinal: int
    content: str
    heading: str = ""
    asset_name: str = ""
    package_name: str = ""


@runtime_checkable
class VectorSearchPort(Protocol):
    async def upsert(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        items: list[IndexedChunk],
        embeddings: list[list[float]],
        package_name: str,
        asset_name: str,
    ) -> None: ...

    async def delete(self, ids: list[UUID]) -> None: ...

    async def search(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        query_embedding: list[float],
        top_k: int,
        kb_ids: tuple[str, ...] = (),
    ) -> list[VectorHit]: ...


class KnowledgeCatalogRepository(ABC):
    @abstractmethod
    async def add_kb(self, kb: KnowledgeBase) -> None: ...

    @abstractmethod
    async def get_kb(self, kb_id: UUID) -> KnowledgeBase | None: ...

    @abstractmethod
    async def list_kbs(self, workspace_id: UUID) -> list[KnowledgeBase]: ...

    @abstractmethod
    async def update_kb(self, kb: KnowledgeBase) -> None: ...

    @abstractmethod
    async def add_doc(self, doc: KnowledgeDoc) -> None: ...

    @abstractmethod
    async def update_doc(self, doc: KnowledgeDoc) -> None: ...

    @abstractmethod
    async def get_doc(self, doc_id: UUID) -> KnowledgeDoc | None: ...

    @abstractmethod
    async def list_docs(self, workspace_id: UUID) -> list[KnowledgeDoc]: ...

    @abstractmethod
    async def add_source(self, source: KnowledgeSource) -> None: ...

    @abstractmethod
    async def list_sources(self, workspace_id: UUID) -> list[KnowledgeSource]: ...

    @abstractmethod
    async def list_tasks(self, workspace_id: UUID) -> list[KnowledgeTask]: ...

    @abstractmethod
    async def list_eval_cases(self, workspace_id: UUID) -> list[KnowledgeEvalCase]: ...

    @abstractmethod
    async def replace_chunks(self, *, doc_id: UUID, chunks: list[IndexedChunk]) -> list[UUID]: ...

    @abstractmethod
    async def list_chunks(
        self, workspace_id: UUID, *, kb_ids: tuple[UUID, ...] = ()
    ) -> list[IndexedChunk]: ...

    @abstractmethod
    async def count_chunks(self, kb_id: UUID) -> int: ...


__all__ = [
    "EmbeddingPort",
    "KnowledgeCatalogRepository",
    "VectorHit",
    "VectorSearchPort",
]
