"""``ContextManifestStore`` 的 SQL 实现 —— manifest 落库 + 摘要写入 ✓。

依据：Context 方案 §5（Persistence）；表结构来自迁移 **0047** ✓。

⚠️ **走 Session 的表** ✓ —— manifest 与摘要都落在 Session 拥有的表上 ✓
（`session_context_manifests` / `agent_sessions` ✓），**保证与轮次同事务**
✓（§6 边界表 ✓）。

⚠️ **manifest 不是事件** ✓ —— 不进 outbox ✓、不投递 ✓（§5.3 ✓）。
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

_INSERT_MANIFEST = """
INSERT INTO session_context_manifests (
    id, tenant_id, workspace_id, session_id, turn_id, step,
    manifest, tokens_total, degraded
) VALUES (
    :id, :tenant_id, :workspace_id, :session_id, :turn_id, :step,
    CAST(:manifest AS jsonb), :tokens_total, CAST(:degraded AS jsonb)
)
"""

_UPDATE_SUMMARY = """
UPDATE agent_sessions
   SET rolling_summary = :summary,
       updated_at = now()
 WHERE id = :session_id AND tenant_id = :tenant_id
"""


class PostgresContextManifestStore:
    """manifest + 摘要的落库 ✓（**自持事务** ✓ —— 与轮次同事务由调用方保证 ✓）。"""

    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def save_manifest(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        session_id: UUID,
        turn_id: UUID,
        step: int,
        manifest: dict[str, Any],
        tokens_total: int,
        degraded: dict[str, Any] | None = None,
    ) -> None:
        """落一条 manifest ✓（每次模型调用一条 ✓）。

        ⚠️ **撞 ``(turn_id, step)` 就是 bug** ✓ —— 直接抛 ✓，不静默覆盖 ✗✗
        （Context 方案 §5.1.1 ✓）。
        """
        try:
            await self._s.execute(
                text(_INSERT_MANIFEST),
                {
                    "id": uuid4(),
                    "tenant_id": tenant_id,
                    "workspace_id": workspace_id,
                    "session_id": session_id,
                    "turn_id": turn_id,
                    "step": step,
                    "manifest": json.dumps(manifest, ensure_ascii=False),
                    "tokens_total": tokens_total,
                    "degraded": json.dumps(degraded or {}, ensure_ascii=False),
                },
            )
            # ⚠️ **立刻 flush** ✓ —— 否则唯一约束要到**提交时**才报 ✗✗
            # （那时报出来的是 DB 的错，不是这里的「这是 bug」 ✗）。
            await self._s.flush()
        except IntegrityError as exc:
            raise RuntimeError(
                f"context manifest already exists for turn={turn_id} step={step}"
            ) from exc

    async def save_rolling_summary(
        self,
        *,
        tenant_id: UUID,
        session_id: UUID,
        summary: str,
    ) -> None:
        """写 ``agent_sessions.rolling_summary`` ✓（新写入的唯一落点 ✓）。"""
        await self._s.execute(
            text(_UPDATE_SUMMARY),
            {"summary": summary, "session_id": session_id, "tenant_id": tenant_id},
        )


__all__ = ["PostgresContextManifestStore"]
