"""向量写入的**共享实现** ✓ —— 两个平面都要用 ✓。

依据：Memory 方案 §10.1（S1 存储）与 §10.2（``_embed_item`` 的去向 ✓）。

⚠️ **为什么要共享** ✓ —— 运行时写入（平面 A）与管理端写入（平面 B）都要
补向量 ✓；各写一份 = 两个实现 ✗✗（向量会不一致 ✗）。

⚠️ **优雅降级** ✓：embedding 不可用（例如 dev 没配真实供应商）时**跳过向量
写入** ✓，不阻塞上层 turn ✓ —— 否则「记忆落库失败」会把整个 turn 掀翻 ✗✗
（用户已经收到回答了 ✗）。目录行仍然保留 ✓，等管理侧配上供应商再补回 ✓。
"""

from __future__ import annotations

import logging
from uuid import UUID

from qzdap.composition.unavailable_providers import ProviderUnavailable
from qzdap.modules.memory.application.ports import (
    EmbeddingPort,
    VectorSearchPort,
)

_log = logging.getLogger(__name__)


async def embed_item(
    embedding: EmbeddingPort | None,
    vectors: VectorSearchPort | None,
    *,
    item_id: UUID,
    layer: str,
    content: str,
    tenant_id: UUID,
    workspace_id: UUID,
    user_id: UUID | None = None,
) -> None:
    """把一条记忆写进向量库 ✓（**失败不抛** ✓ —— 降级 ✓）。"""
    if embedding is None or vectors is None or not content.strip():
        return
    try:
        [vector] = await embedding.embed([content])
    except ProviderUnavailable:
        _log.warning(
            "memory embed skipped (provider unavailable) item_id=%s layer=%s",
            item_id,
            layer,
        )
        return
    await vectors.upsert(
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        item_id=item_id,
        layer=layer,
        content=content,
        embedding=vector,
        user_id=user_id,
    )


__all__ = ["embed_item"]
