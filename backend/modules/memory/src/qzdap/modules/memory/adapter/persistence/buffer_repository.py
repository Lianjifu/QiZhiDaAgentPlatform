"""**会话缓冲**的仓储 ✓（决策 #5 ✓ —— L1 退役的落点 ✓）。

⚠️ **只放缓冲里** ✓ —— 提炼成 L2 是**另一件事** ✓（`memory/refine.py` ✓）。
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from qzdap.modules.memory.adapter.persistence.models import (
    SessionMemoryBufferORM,
)
from qzdap_agent_runtime.memory.refine import BufferRow, SessionBufferView


class SqlMemoryBufferRepository:
    """``session_memory_buffer`` 的读写 ✓。"""

    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def add(self, row: BufferRow) -> None:
        """**加一条** ✓（同会话同内容**唯一** ✓ —— 重复不重复写 ✓）。"""
        stmt = select(SessionMemoryBufferORM).where(
            SessionMemoryBufferORM.session_id == row.session_id,
            SessionMemoryBufferORM.content_hash == row.content_hash,
        )
        existing = (await self._s.execute(stmt)).scalars().first()
        if existing is not None:
            return
        self._s.add(
            SessionMemoryBufferORM(
                id=row.id,
                tenant_id=row.tenant_id,
                workspace_id=row.workspace_id,
                session_id=row.session_id,
                user_id=row.user_id,
                turn_id=row.turn_id,
                content=row.content,
                content_hash=row.content_hash,
                candidates={},
                status="buffer",
                created_at=row.created_at,
            )
        )

    async def list_pending(self, *, before: datetime, limit: int = 100) -> list[BufferRow]:
        """**待提炼** 的行 ✓（按创建时间 ✓）。"""
        stmt = (
            select(SessionMemoryBufferORM)
            .where(SessionMemoryBufferORM.status == "buffer")
            .where(SessionMemoryBufferORM.created_at <= before)
            .order_by(SessionMemoryBufferORM.created_at.asc())
            .limit(max(1, limit))
        )
        rows = (await self._s.execute(stmt)).scalars().all()
        return [
            BufferRow(
                id=row.id,
                tenant_id=row.tenant_id,
                workspace_id=row.workspace_id,
                session_id=row.session_id,
                user_id=row.user_id,
                turn_id=row.turn_id,
                content=row.content,
                content_hash=row.content_hash,
                created_at=row.created_at,
            )
            for row in rows
        ]

    async def delete(self, row_ids: tuple[UUID, ...]) -> None:
        """**删掉已处理的行** ✓（提炼完 / 丢弃后 ✓ —— 不留垃圾 ✓）。"""
        if not row_ids:
            return
        await self._s.execute(
            delete(SessionMemoryBufferORM).where(SessionMemoryBufferORM.id.in_(row_ids))
        )

    # ── 管理面（L1 表退役后的唯一来源 ✓ —— M-46 ✓）──────────────────

    async def list_workspace_views(self, *, workspace_id: UUID) -> list[SessionBufferView]:
        """**工作区下每个会话的缓冲概览** ✓（按会话聚合 ✓）。"""
        stmt = (
            select(
                SessionMemoryBufferORM.session_id,
                func.min(SessionMemoryBufferORM.created_at).label("first_at"),
                func.max(SessionMemoryBufferORM.created_at).label("last_at"),
                func.count().label("items"),
                func.sum(func.length(SessionMemoryBufferORM.content)).label("chars"),
            )
            .where(SessionMemoryBufferORM.workspace_id == workspace_id)
            .where(SessionMemoryBufferORM.status == "buffer")
            .group_by(SessionMemoryBufferORM.session_id)
            .order_by(func.max(SessionMemoryBufferORM.created_at).desc())
        )
        rows = (await self._s.execute(stmt)).all()
        if not rows:
            return []
        # ⚠️ **用户与工作区按会话补齐** ✓（聚合行里没有 ✓ —— 要再查一次 ✓）。
        session_ids = [row.session_id for row in rows]
        details = (
            await self._s.execute(
                select(
                    SessionMemoryBufferORM.session_id,
                    SessionMemoryBufferORM.user_id,
                    SessionMemoryBufferORM.workspace_id,
                )
                .where(SessionMemoryBufferORM.session_id.in_(session_ids))
                .distinct()
            )
        ).all()
        by_session = {row.session_id: row for row in details}
        return [
            SessionBufferView(
                session_id=row.session_id,
                workspace_id=by_session[row.session_id].workspace_id,
                user_id=by_session[row.session_id].user_id,
                items=int(row.items),
                total_chars=int(row.chars or 0),
                created_at=row.first_at,
                last_write_at=row.last_at,
            )
            for row in rows
            if row.session_id in by_session
        ]

    async def list_session_rows(self, *, session_id: UUID) -> list[BufferRow]:
        """**某个会话的缓冲条目** ✓（详情页 ✓）。"""
        stmt = (
            select(SessionMemoryBufferORM)
            .where(SessionMemoryBufferORM.session_id == session_id)
            .where(SessionMemoryBufferORM.status == "buffer")
            .order_by(SessionMemoryBufferORM.created_at.asc())
        )
        rows = (await self._s.execute(stmt)).scalars().all()
        return [
            BufferRow(
                id=row.id,
                tenant_id=row.tenant_id,
                workspace_id=row.workspace_id,
                session_id=row.session_id,
                user_id=row.user_id,
                turn_id=row.turn_id,
                content=row.content,
                content_hash=row.content_hash,
                created_at=row.created_at,
            )
            for row in rows
        ]

    async def delete_session(self, *, session_id: UUID) -> int:
        """**冲掉一个会话的缓冲** ✓（返回冲掉几条 ✓）。"""
        result = await self._s.execute(
            delete(SessionMemoryBufferORM).where(SessionMemoryBufferORM.session_id == session_id)
        )
        return int(result.rowcount or 0)


__all__ = ["SqlMemoryBufferRepository"]
