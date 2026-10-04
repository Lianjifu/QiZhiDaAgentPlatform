"""Vector store Protocol + DTOs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol
from uuid import UUID


@dataclass(slots=True, frozen=True)
class VectorItem:
    id: UUID
    tenant_id: UUID
    workspace_id: UUID | None
    embedding: list[float]
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class SearchResult:
    id: UUID
    score: float
    payload: dict[str, Any]


class VectorStore(Protocol):
    async def upsert(self, items: list[VectorItem]) -> None: ...
    async def search(
        self,
        query: VectorItem,
        *,
        top_k: int = 10,
        filter: dict[str, Any] | None = None,
    ) -> list[SearchResult]: ...
    async def delete(self, ids: list[UUID]) -> None: ...
