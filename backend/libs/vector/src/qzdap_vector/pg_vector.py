"""pgvector implementation.

Reads `tenant_id` from each `VectorItem` and includes it in upsert + search
SQL. The `filter` arg is AND-merged into the WHERE clause.

Filter keys must be safe SQL identifiers (``[A-Za-z_][A-Za-z0-9_]*``) — they
are used as bind parameter names in the generated SQL, and arbitrary input
would either break the parameter name or smuggle SQL fragments.
"""

from __future__ import annotations

import json
import re
from typing import Any
from uuid import UUID

from qzdap_persistence.pgvector import register_pgvector
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from qzdap_vector.store import SearchResult, VectorItem, VectorStore

_SAFE_FILTER_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _vec_bind(embedding: list[float] | tuple[float, ...]) -> str:
    """Pre-encode ``list[float]`` as the textual pgvector literal.

    asyncpg's prepared-statement binder does not understand pgvector's
    ``vector`` column type — passing a Python list through raw ``text()``
    produces ``expected str, got list``. We use the pgvector sqlalchemy
    type's bind_processor so the encoding stays consistent with pgvector.
    """
    from pgvector.sqlalchemy import VECTOR

    return VECTOR().bind_processor(None)(list(embedding))  # type: ignore[arg-type]


def _jsonb_bind(value: Any) -> str:
    """Pre-encode a Python object as a JSON string for jsonb columns."""
    return json.dumps(value, default=str)


class PgVectorStore(VectorStore):
    def __init__(
        self,
        engine: AsyncEngine,
        *,
        table: str = "memory_embeddings",
        dim: int = 1536,
    ) -> None:
        register_pgvector()
        self._engine = engine
        self._table = table
        self._dim = dim

    async def ensure_schema(self) -> None:
        async with self._engine.begin() as conn:
            await conn.execute(
                text(
                    f"""
                    CREATE EXTENSION IF NOT EXISTS vector;
                    CREATE TABLE IF NOT EXISTS {self._table} (
                        id UUID PRIMARY KEY,
                        tenant_id UUID NOT NULL,
                        workspace_id UUID,
                        embedding vector({self._dim}) NOT NULL,
                        payload JSONB NOT NULL DEFAULT '{{}}'::jsonb
                    );
                    CREATE INDEX IF NOT EXISTS ix_{self._table}_tenant_id
                        ON {self._table} (tenant_id);
                    """
                )
            )

    async def upsert(self, items: list[VectorItem]) -> None:
        if not items:
            return
        async with self._engine.begin() as conn:
            for item in items:
                await conn.execute(
                    text(
                        f"""
                        INSERT INTO {self._table} (id, tenant_id, workspace_id, embedding, payload)
                        VALUES (:id, :tid, :wid, :vec, :payload)
                        ON CONFLICT (id) DO UPDATE SET
                            embedding = EXCLUDED.embedding,
                            payload = EXCLUDED.payload
                        """
                    ),
                    {
                        "id": str(item.id),
                        "tid": str(item.tenant_id),
                        "wid": str(item.workspace_id) if item.workspace_id else None,
                        "vec": _vec_bind(item.embedding),
                        "payload": _jsonb_bind(item.payload),
                    },
                )

    async def search(
        self,
        query: VectorItem,
        *,
        top_k: int = 10,
        filter: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        clauses = ["tenant_id = :tid"]
        params: dict[str, Any] = {
            "tid": str(query.tenant_id),
            "vec": _vec_bind(query.embedding),
            "k": top_k,
        }
        if filter:
            for k, v in filter.items():
                if not _SAFE_FILTER_KEY.match(k):
                    raise ValueError(
                        f"invalid filter key {k!r}: must match "
                        r"[A-Za-z_][A-Za-z0-9_]*"
                    )
                key = f"f_{k}"
                clauses.append(
                    f"(payload ->> CAST(:{key} AS text)) = CAST(:{key}_v AS text)"
                )
                params[key] = k
                params[f"{key}_v"] = str(v)

        sql = f"""
            SELECT id, payload,
                   1 - (embedding <=> :vec) AS score
            FROM {self._table}
            WHERE {" AND ".join(clauses)}
            ORDER BY embedding <=> :vec
            LIMIT :k
        """
        async with self._engine.connect() as conn:
            rows = await conn.execute(text(sql), params)
            return [
                SearchResult(
                    id=row.id, score=float(row.score), payload=dict(row.payload)
                )
                for row in rows
            ]

    async def delete(self, ids: list[UUID]) -> None:
        if not ids:
            return
        async with self._engine.begin() as conn:
            await conn.execute(
                text(f"DELETE FROM {self._table} WHERE id = ANY(:ids)"),
                {"ids": [str(i) for i in ids]},
            )
