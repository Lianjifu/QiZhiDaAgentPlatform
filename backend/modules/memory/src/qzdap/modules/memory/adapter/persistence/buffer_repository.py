"""**会话缓冲**的仓储 ✓（决策 #5 ✓ —— L1 退役的落点 ✓）。

⚠️ **只放缓冲里** ✓ —— 提炼成 L2 是**另一件事** ✓（`memory/refine.py` ✓）。
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from qzdap.modules.memory.adapter.persistence.models import (
    SessionMemoryBufferORM,
)
from qzdap_agent_runtime.memory.refine import BufferRow


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


__all__ = ["SqlMemoryBufferRepository"]
