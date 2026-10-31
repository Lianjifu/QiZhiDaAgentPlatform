"""写入端口的**模块侧实现** ✓ —— 把仓储包装成契约层的 ``MemoryWritePort`` ✓。

依据：Memory 方案 §4（写入五步 ✓）、§4.4（幂等与去重 ✓）、§4.5（置信度 ✓）。

⚠️ **落库带 provenance** ✓（``user_id`` / ``source_turn_id`` / ``content_hash`` ✓）
—— 「每条记忆可追溯到来源轮次」✓（验收 ✓）。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from qzdap.modules.memory.application.ports import (
    EmbeddingPort,
    MemoryCatalogRepository,
    VectorSearchPort,
)
from qzdap.modules.memory.domain.entities import L2Fact
from qzdap_agent_runtime.memory.refine import BufferPort, BufferRow
from qzdap_agent_runtime.memory.vectorize import (
    VectorWriteQueuePort,
    VectorWriteRequest,
)
from qzdap_agent_runtime.memory.writer import CONTENT_HASH_VERSION


class MemoryWriteAdapter:
    """记忆的落库 ✓（契约层不碰数据库 ✓）。"""

    def __init__(
        self,
        catalog: MemoryCatalogRepository,
        *,
        embedding: EmbeddingPort | None = None,
        vectors: VectorSearchPort | None = None,
        vector_queue: VectorWriteQueuePort | None = None,
        buffer: BufferPort | None = None,
    ) -> None:
        self._catalog = catalog
        self._embedding = embedding
        self._vectors = vectors
        #: ⚠️ **会话缓冲** ✓（决策 #5 ✓）—— 会话级策略写这里 ✓。
        self._buffer = buffer
        #: ⚠️ **向量补写队列** ✓（C5 ✓ —— §5.4 ✓）—— 有它就**不内联调
        #: embedding** ✓（不阻塞对话 ✓）；没有它就退回**内联补写** ✓
        #: （测试与单进程场景 ✓ —— 行为一致 ✓，只是慢一点 ✓）。
        self._vector_queue = vector_queue

    async def find_by_hash(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        user_id: UUID,
        content_hash: str,
    ) -> dict[str, Any] | None:
        """按哈希查已有条目 ✓（**去重** ✓ —— §4.4 ✓）。"""
        _ = tenant_id
        existing = await self._catalog.find_l2_by_hash(
            workspace_id, user_id=user_id, content_hash=content_hash
        )
        if existing is None:
            return None
        return {"id": str(existing.id)}

    async def save(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        user_id: UUID,
        session_id: UUID,
        turn_id: UUID | None,
        content: str,
        content_hash: str,
        confidence: float,
        confidence_source: str,
        category: str,
        target: str = "l2",
    ) -> dict[str, Any]:
        """落一条记忆 ✓（带 provenance ✓）。

        ⚠️ **``target='buffer'`` → 落会话缓冲** ✓（§7.1 ✓ —— 会话级策略 ✓）——
        会话结束后**提炼成 L2** ✓（``memory/refine.py`` ✓）。
        """
        now = datetime.now(UTC)
        if target == "buffer":
            return await self._save_to_buffer(
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                user_id=user_id,
                session_id=session_id,
                turn_id=turn_id,
                content=content,
                content_hash=content_hash,
                confidence=confidence,
                confidence_source=confidence_source,
                category=category,
                now=now,
            )
        return await self._save_to_l2(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            user_id=user_id,
            session_id=session_id,
            turn_id=turn_id,
            content=content,
            content_hash=content_hash,
            confidence=confidence,
            confidence_source=confidence_source,
            category=category,
            now=now,
        )

    async def _save_to_l2(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        user_id: UUID,
        session_id: UUID,
        turn_id: UUID | None,
        content: str,
        content_hash: str,
        confidence: float,
        confidence_source: str,
        category: str,
        now: datetime,
    ) -> dict[str, Any]:
        """**落一条 L2 记忆** ✓（带 provenance ✓）。"""
        fact = L2Fact(
            id=uuid4(),
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            user_name="用户",
            user_id=user_id,
            key=content[:64],
            value=content,
            category=category,  # type: ignore[arg-type]
            source_session=str(session_id),
            confidence=confidence,
            status="confirmed",
            promoted_to_l3=False,
            updated_at=now,
            created_at=now,
            usage_history=[],
            content_hash=content_hash,
            content_hash_version=CONTENT_HASH_VERSION,
            source_turn_id=turn_id,
            used_count=1,
            confidence_source=confidence_source,
            version=1,
        )
        await self._catalog.add_l2(fact)
        await self._embed(
            fact,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            session_id=session_id,
        )
        return fact.to_admin_dict()

    async def _save_to_buffer(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        user_id: UUID,
        session_id: UUID,
        turn_id: UUID | None,
        content: str,
        content_hash: str,
        confidence: float,
        confidence_source: str,
        category: str,
        now: datetime,
    ) -> dict[str, Any]:
        """**落会话缓冲** ✓（决策 #5 ✓）。

        ⚠️ **没有缓冲口就退回 L2** ✓ —— 不静默丢弃 ✓（否则会话级策略的记忆
        就没了 ✗✗）。
        """
        if self._buffer is None:
            return await self._save_to_l2(
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                user_id=user_id,
                session_id=session_id,
                turn_id=turn_id,
                content=content,
                content_hash=content_hash,
                confidence=confidence,
                confidence_source=confidence_source,
                category=category,
                now=now,
            )
        row = BufferRow(
            id=uuid4(),
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            session_id=session_id,
            user_id=user_id,
            turn_id=turn_id,
            content=content,
            content_hash=content_hash,
            created_at=now,
        )
        await self._buffer.add(row)
        return {
            "id": str(row.id),
            "layer": "buffer",
            "content": content,
            "confidence": confidence,
            "confidence_source": confidence_source,
            "category": category,
        }

    async def touch(self, *, item_id: str) -> None:
        """命中重复 → **只更新用量** ✓（不新增 ✓ —— §4.4 ✓）。"""
        from uuid import UUID as _UUID

        try:
            parsed = _UUID(item_id)
        except ValueError:
            return
        fact = await self._catalog.get_l2(parsed)
        if fact is None:
            return
        now = datetime.now(UTC)
        fact.used_count = int(fact.used_count or 0) + 1
        fact.last_used_at = now
        fact.updated_at = now
        await self._catalog.update_l2(fact)

    async def _embed(
        self,
        fact: L2Fact,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        session_id: UUID | None = None,
    ) -> None:
        """**排一条向量补写** ✓（C5 ✓ —— §5.4 ✓）。

        ⚠️ **有队列就排队** ✓ —— 写路径**不等 embedding** ✓（不阻塞对话 ✓）；
        ⚠️ **没队列就内联补写** ✓（行为一致 ✓ —— 只是慢 ✓）。
        ⚠️ **补不上不影响记忆落库** ✓（§5.4 的降级口径 ✓ —— 召回侧降级为
        纯词法 ✓，兜底补写会把它捡回来 ✓）。
        """
        if self._embedding is None or self._vectors is None:
            return
        request = VectorWriteRequest(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            item_id=fact.id,
            layer="l2",
            content=fact.recall_text(),
            user_id=fact.user_id,
            session_id=session_id,
        )
        if self._vector_queue is not None:
            self._vector_queue.enqueue(request)
            return
        try:
            [vector] = await self._embedding.embed([request.content])
        except Exception:
            return
        await self._vectors.upsert(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            item_id=fact.id,
            layer="l2",
            content=request.content,
            embedding=vector,
            user_id=fact.user_id,
            # ⚠️ **会话作用域要进向量 payload** ✓（§7.1 ✓）—— 否则会话级
            # 召回会看到别的会话的记忆 ✗✗。
            session_id=session_id,
        )


__all__ = ["MemoryWriteAdapter"]
