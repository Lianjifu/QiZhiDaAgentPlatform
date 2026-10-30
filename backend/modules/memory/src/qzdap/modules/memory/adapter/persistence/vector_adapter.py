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
        user_id: UUID | None = None,
        session_id: UUID | None = None,
    ) -> None:
        payload: dict[str, str] = {
            "workspace_id": str(workspace_id),
            "layer": layer,
            "content": content,
        }
        if user_id is not None:
            # 决策 #2：向量 payload 带 user_id，让过滤能下推到 pgvector。
            payload["user_id"] = str(user_id)
        if session_id is not None:
            # ⚠️ **会话作用域也要下推到向量过滤** ✓（§7.1 ✓）—— 否则会话级
            # 召回会看到别的会话的记忆 ✗✗。
            payload["session_id"] = str(session_id)
        await self._store.upsert(
            [
                VectorItem(
                    id=item_id,
                    tenant_id=tenant_id,
                    workspace_id=workspace_id,
                    embedding=list(embedding),
                    payload=payload,
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
        user_id: UUID | None = None,
        session_id: UUID | None = None,
    ) -> list[VectorHit]:
        query = VectorItem(
            id=UUID(int=0),
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            embedding=list(query_embedding),
            payload={"workspace_id": str(workspace_id)},
        )
        filters: dict[str, str] = {"workspace_id": str(workspace_id)}
        if session_id is not None:
            # ⚠️ **存量向量没有 session_id payload** → 匹配不上 → 被排除 ✓
            # （与 user_id 同一口径 ✓ —— 不可见，好过串会话 ✗✗）。
            filters["session_id"] = str(session_id)
        if user_id is not None:
            # ⚠️ 存量向量没有 user_id payload → `payload->>'user_id'` 为 NULL →
            # 不匹配 → 被排除。这正是决策 #11 要的方向（不可见，不要串号）。
            filters["user_id"] = str(user_id)
        results = await self._store.search(query, top_k=max(top_k, 1), filter=filters)
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
