"""向量补写的**模块侧实现** ✓（C5 —— Memory 方案 §5.4 ✓）。

⚠️ **embedding 与向量库在这里** ✓ —— 契约层只编排 ✓（§10.1 的 S1 ✓）。

⚠️ **删除同步删向量** ✓（§5.4 ✓）—— 否则向量成为**残留副本** ✓✗。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from qzdap_agent_runtime.memory.vectorize import (
    VectorWriteRequest,
)

from qzdap.modules.memory.application.ports import (
    EmbeddingPort,
    VectorSearchPort,
)


class MemoryVectorizeAdapter:
    """**补写向量 / 删向量** ✓（§5.4 ✓）。"""

    def __init__(
        self,
        *,
        embedding: EmbeddingPort | None,
        vectors: VectorSearchPort | None,
    ) -> None:
        self._embedding = embedding
        self._vectors = vectors

    async def upsert(self, request: VectorWriteRequest) -> None:
        """补写一条向量 ✓（**失败要抛** ✓ —— 由 worker 重试 ✓）。"""
        if self._embedding is None or self._vectors is None:
            # ⚠️ **没配向量就当「已完成」** ✓ —— 否则 worker 会无限重试 ✗✗。
            return
        [vector] = await self._embedding.embed([request.content])
        await self._vectors.upsert(
            tenant_id=request.tenant_id,
            workspace_id=request.workspace_id,
            item_id=request.item_id,
            layer=request.layer,
            content=request.content,
            embedding=vector,
            user_id=request.user_id,
            session_id=request.session_id,
        )

    async def delete(self, item_ids: tuple[UUID, ...]) -> None:
        """删向量 ✓（**同步删** ✓ —— 不留残留副本 ✓）。"""
        if self._vectors is None or not item_ids:
            return
        await self._vectors.delete(item_ids)


class MemoryVectorBackfill:
    """**兜底补写**的来源 ✓（§5.4 ✓ —— 「由 C10 兜底补写」✓）。

    ⚠️ **判据是「最近更新过」** ✓ —— 不去逐条比对向量表 ✓（那是全表扫描
    ✗✗）→ 代价是**重复补写** ✓（``upsert`` 是幂等的 ✓ —— 不产生副本 ✓）。

    ⚠️ **自己开会话** ✓ —— 它是**维护任务** ✓（跨租户扫描 ✓ —— 不能借用
    请求的会话 ✓ —— 那是另一个租户的上下文 ✗✗）。
    """

    def __init__(
        self,
        session_factory: Any,
        *,
        window_minutes: int = 60,
    ) -> None:
        self._session_factory = session_factory
        self._window = timedelta(minutes=max(1, window_minutes))

    async def find_missing(self, *, limit: int = 100) -> list[VectorWriteRequest]:
        """**最近更新过的 L2** ✓（重新排进补写队列 ✓）。"""
        since = datetime.now(UTC) - self._window
        from qzdap.modules.memory.adapter.persistence.repositories import (
            SqlMemoryCatalogRepository,
        )

        async with self._session_factory() as session:
            rows = await SqlMemoryCatalogRepository(
                session
            ).list_l2_updated_since(since, limit=max(1, limit))
        return [
            VectorWriteRequest(
                tenant_id=row.tenant_id,
                workspace_id=row.workspace_id,
                item_id=row.id,
                layer="l2",
                content=row.recall_text(),
                user_id=row.user_id,
                session_id=_as_uuid(row.source_session),
            )
            for row in rows
        ]


def _as_uuid(raw: str | None) -> UUID | None:
    if not raw:
        return None
    try:
        return UUID(str(raw))
    except ValueError:
        return None


__all__ = ["MemoryVectorBackfill", "MemoryVectorizeAdapter"]
