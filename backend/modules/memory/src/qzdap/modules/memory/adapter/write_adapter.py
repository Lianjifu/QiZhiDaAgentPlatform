"""写入端口的**模块侧实现** ✓ —— 把仓储包装成契约层的 ``MemoryWritePort`` ✓。

依据：Memory 方案 §4（写入五步 ✓）、§4.4（幂等与去重 ✓）、§4.5（置信度 ✓）。

⚠️ **落库带 provenance** ✓（``user_id`` / ``source_turn_id`` / ``content_hash`` ✓）
—— 「每条记忆可追溯到来源轮次」✓（验收 ✓）。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from qzdap_agent_runtime.memory.writer import CONTENT_HASH_VERSION

from qzdap.modules.memory.application.ports import (
    EmbeddingPort,
    MemoryCatalogRepository,
    VectorSearchPort,
)
from qzdap.modules.memory.domain.entities import L2Fact


class MemoryWriteAdapter:
    """记忆的落库 ✓（契约层不碰数据库 ✓）。"""

    def __init__(
        self,
        catalog: MemoryCatalogRepository,
        *,
        embedding: EmbeddingPort | None = None,
        vectors: VectorSearchPort | None = None,
    ) -> None:
        self._catalog = catalog
        self._embedding = embedding
        self._vectors = vectors

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
    ) -> dict[str, Any]:
        """落一条 L2 记忆 ✓（带 provenance ✓）。"""
        now = datetime.now(UTC)
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
        await self._embed(fact, tenant_id=tenant_id, workspace_id=workspace_id)
        return fact.to_admin_dict()

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
        self, fact: L2Fact, *, tenant_id: UUID, workspace_id: UUID
    ) -> None:
        """向量补写 ✓（失败不阻塞 ✓ —— 降级 ✓）。"""
        if self._embedding is None or self._vectors is None:
            return
        try:
            [vector] = await self._embedding.embed([fact.recall_text()])
        except Exception:  # noqa: BLE001
            return
        await self._vectors.upsert(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            item_id=fact.id,
            layer="l2",
            content=fact.recall_text(),
            embedding=vector,
            user_id=fact.user_id,
        )


__all__ = ["MemoryWriteAdapter"]
