"""``SessionSequencePort`` 的 SQL 实现 —— 会话内两个序列的**原子分配器**。

依据：Session 方案 §5.2。

⚠️ **为什么是 ``UPDATE ... SET x = x + 1 RETURNING``**：分配必须与写号在
**同一个事务**里完成 —— 两次独立的读-改-写之间会插进另一个写者，两个写者
拿到同一个号 → 撞上唯一索引 ``(session_id, ingress_seq)`` /
``(session_id, session_seq)`` ✗✗。

⚠️ **租户过滤写进 WHERE** —— 不依赖请求上下文里绑定的租户（没绑定时 ORM 的
自动过滤会退化成 no-op，查询就跨租户了）。
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import update

from qzdap.modules.agent_runtime.adapter.persistence.models import SessionORM
from qzdap.modules.agent_runtime.domain.errors import SessionNotFound


class PostgresSessionSequence:
    """会话内两个序列的分配器（同一个 DB 会话 → 同一个事务 ✓）。"""

    def __init__(self, session: Any) -> None:
        self._s = session

    async def next_ingress_seq(self, *, tenant_id: UUID, session_id: UUID) -> int:
        """分配下一个**入站序号**（轮次序）—— 调用方是 Router ✓。"""
        return await self._bump(
            SessionORM.next_ingress_seq, tenant_id=tenant_id, session_id=session_id
        )

    async def next_message_seq(self, *, tenant_id: UUID, session_id: UUID) -> int:
        """分配下一个**会话内消息序号** ✓。"""
        return await self._bump(
            SessionORM.next_message_seq, tenant_id=tenant_id, session_id=session_id
        )

    async def _bump(
        self, column: Any, *, tenant_id: UUID, session_id: UUID
    ) -> int:
        result = await self._s.execute(
            update(SessionORM)
            .where(
                SessionORM.id == session_id,
                SessionORM.tenant_id == tenant_id,
            )
            .values({column: column + 1})
            .returning(column)
        )
        value = result.scalar_one_or_none()
        if value is None:
            raise SessionNotFound(f"session {session_id} not found")
        return int(value)


__all__ = ["PostgresSessionSequence"]
