"""PgVectorStore adapter for knowledge chunk embeddings."""

from __future__ import annotations

from uuid import UUID

from qzdap_vector.pg_vector import PgVectorStore
from qzdap_vector.store import VectorItem

from qzdap.modules.knowledge.application.ports import VectorHit, VectorSearchPort
from qzdap.modules.knowledge.domain.entities import IndexedChunk


class PgKnowledgeVectorAdapter(VectorSearchPort):
    def __init__(self, store: PgVectorStore) -> None:
        self._store = store

    async def upsert(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        items: list[IndexedChunk],
        embeddings: list[list[float]],
        package_name: str,
        asset_name: str,
    ) -> None:
        rows = [
            VectorItem(
                id=chunk.id,
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                embedding=list(vector),
                payload={
                    "workspace_id": str(workspace_id),
                    "kb_id": str(chunk.kb_id),
                    "doc_id": str(chunk.doc_id),
                    "ordinal": str(chunk.ordinal),
                    "content": chunk.content,
                    "heading": chunk.heading,
                    "package_name": package_name,
                    "asset_name": asset_name,
                },
            )
            for chunk, vector in zip(items, embeddings, strict=True)
        ]
        await self._store.upsert(rows)

    async def delete(self, ids: list[UUID]) -> None:
        await self._store.delete(ids)

    async def search(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        query_embedding: list[float],
        top_k: int,
        kb_ids: tuple[str, ...] = (),
    ) -> list[VectorHit]:
        allowed = set(kb_ids)
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
        hits: list[VectorHit] = []
        for row in results:
            payload = row.payload or {}
            kb_id = str(payload.get("kb_id") or "")
            if allowed and kb_id not in allowed:
                continue
            hits.append(
                VectorHit(
                    chunk_id=row.id,
                    score=float(row.score),
                    kb_id=kb_id,
                    doc_id=str(payload.get("doc_id") or ""),
                    ordinal=int(payload.get("ordinal") or 0),
                    content=str(payload.get("content") or ""),
                    heading=str(payload.get("heading") or ""),
                    asset_name=str(payload.get("asset_name") or ""),
                    package_name=str(payload.get("package_name") or ""),
                )
            )
        return hits[:top_k]


__all__ = ["PgKnowledgeVectorAdapter"]
