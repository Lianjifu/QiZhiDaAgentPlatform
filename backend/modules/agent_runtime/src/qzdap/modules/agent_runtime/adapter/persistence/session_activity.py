"""**会话还在不在** ✓ —— Memory 的窄端口实现 ✓（§7.1 ✓）。

⚠️ **会话表归 Session 层** ✓ —— Memory **不查它** ✓ → 由这里回答 ✓
（窄端口 ✓ —— Memory 方案 §8 的边界 ✓）。

⚠️ **判据是「还有活动轮次」** ✓ —— `current_turn_id` ✓（执行权 ✓）+
``session_turns`` 里**在跑或排队**的轮次 ✓（排队也算活动 ✓ —— 否则会把
正在排队的会话提前提炼 ✗✗）。
"""

from __future__ import annotations

from uuid import UUID

from qzdap_agent_runtime.memory.refine import SessionActivityPort
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from qzdap.modules.agent_runtime.adapter.persistence.models import (
    SessionORM,
    SessionTurnORM,
)


class PostgresSessionActivity(SessionActivityPort):
    """**活动会话**的查询 ✓（模块侧实现 ✓ —— 它拥有那两张表 ✓）。"""

    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def active_session_ids(
        self, *, session_ids: tuple[UUID, ...]
    ) -> set[UUID]:
        """**还在跑**的会话 ✓（空的 = 都结束了 ✓）。"""
        if not session_ids:
            return set()
        # ⚠️ **判据是「有活动轮次」** ✓ —— 不是「会话开着」✓（会话大多数
        # 时候都是开着的 ✗✗ —— 那样就永远不提炼了 ✗✗）。
        stmt = select(SessionORM.id).where(
            SessionORM.id.in_(session_ids),
            SessionORM.current_turn_id.isnot(None),
        )
        active = set((await self._s.execute(stmt)).scalars().all())
        if not active:
            return set()
        turn_stmt = select(SessionTurnORM.session_id).where(
            SessionTurnORM.session_id.in_(tuple(active)),
            SessionTurnORM.status.in_(("running", "queued")),
        )
        active |= set((await self._s.execute(turn_stmt)).scalars().all())
        return active


__all__ = ["PostgresSessionActivity"]
