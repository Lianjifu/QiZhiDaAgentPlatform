"""``PostgresSessionCostStore`` —— **会话累计成本** ✓（跨轮累加 ✓）。

⚠️ **为什么要有它** ✓ —— 成本闸门之前只看**这一轮** ✓ → 预算**每轮重置** ✓
→ 一个会话可以烧掉 N 倍的钱而**没人拦得住** ✗✗。现在闸门看的是
**「之前那些轮 + 这一轮」** ✓。

⚠️ **数据在 ``session_turns.cost_usd``** ✓ —— 每一轮结束时写进去 ✓
（契约层的 ``finish_turn`` ✓）—— 这里只**求和** ✓，不另存一份 ✓
（两份账本迟早对不上 ✗✗）。
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_SUM_SESSION_COST = """
SELECT COALESCE(SUM(cost_usd), 0)
  FROM session_turns
 WHERE session_id = :session_id
   AND tenant_id = :tenant_id
"""


class PostgresSessionCostStore:
    """**会话累计成本** ✓（只读 ✓）。"""

    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def sum_cost(self, *, tenant_id: UUID, session_id: UUID) -> float:
        """**这个会话到目前为止花了多少钱** ✓（美元 ✓）。

        ⚠️ **查不到就是 0** ✓ —— 不是错误 ✓（没有历史轮次 ✓ = 没花过 ✓）。
        """
        result = await self._s.execute(
            text(_SUM_SESSION_COST),
            {"session_id": session_id, "tenant_id": tenant_id},
        )
        return float(result.scalar() or 0.0)


__all__ = ["PostgresSessionCostStore"]
