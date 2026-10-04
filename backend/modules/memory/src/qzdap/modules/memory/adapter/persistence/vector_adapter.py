"""PgVectorStore adapter for L2/L3 memory recall."""

from __future__ import annotations

from uuid import UUID

from qzdap_vector.pg_vector import PgVectorStore
from qzdap_vector.store import VectorItem

from qzdap.modules.memory.application.ports import VectorHit, VectorSearchPort


class PgMemoryVectorAdapter(VectorSearchPort):
    def __init__(self, store: PgVectorStore) -> None:
        self._store = store

    async def upsert(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        item_id: UUID,
        layer: str,
        content: str,
        embedding: list[float],
    ) -> None:
        await self._store.upsert(
            [
                VectorItem(
                    id=item_id,
                    tenant_id=tenant_id,
                    workspace_id=workspace_id,
                    embedding=list(embedding),
                    payload={
                        "workspace_id": str(workspace_id),
                        "layer": layer,
                        "content": content,
                    },
                )
            ]
        )

    async def delete(self, ids: list[UUID]) -> None:
        await self._store.delete(ids)

    async def search(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        query_embedding: list[float],
        top_k: int,
    ) -> list[VectorHit]:
        query = VectorItem(
            id=UUID(int=0),
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            embedding=list(query_embedding),
            payload={"workspace_id": str(workspace_id)},
        )
        results = await self._store.search(
            query, top_k=max(top_k, 1), filter={"workspace_id": str(workspace_id)}
        )
        return [
            VectorHit(
                item_id=row.id,
                score=float(row.score),
                layer=str((row.payload or {}).get("layer") or "l2"),
                content=str((row.payload or {}).get("content") or ""),
            )
            for row in results
        ]


__all__ = ["PgMemoryVectorAdapter"]
