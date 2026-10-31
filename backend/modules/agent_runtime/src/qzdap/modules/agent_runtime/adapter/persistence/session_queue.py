"""``TurnQueuePort`` 的 SQL 实现 —— 同会话的**有序处理**（Router 方案 §4.2）。

⚠️ **放行只有一个权威** ✓（决策 #9 ✓）—— 轮次行的**状态 CAS** ✓：

```sql
UPDATE session_turns SET status = 'running' WHERE id = :turn_id AND status = 'queued'
```

只有**原子地**把状态从 ``queued`` 改成 ``running`` 的那个 worker 才能执行 ✓
—— 不需要任何跨事务锁 ✓（``pg_try_advisory_xact_lock`` 在事务提交时就释放 ✗✗
—— 轮次是**长流式执行** ✓，锁随短事务提交而释放就等于没有互斥 ✗✗）。

⚠️ **两级判定** ✓（Router 方案 §4.2 ✓）：

| 级 | 判据 | 动作 |
|---|---|---|
| **快路径** ✓ | ``turn.ingress_seq == session.last_completed_seq + 1`` ✓ | 直接放行 ✓ |
| **兜底路径** ✓ | 快路径不成立 ✓ 但 ``session_turns`` 里有更大的 ``succeeded`` ✓ | **以权威值为准放行** ✓ + **修快照** ✓ + **计数告警** ✓ |

⚠️ **审批挂起不占执行位** ✓（决策 #6 ✓）—— 判据里看的是 ``status='running'``
✓（等待审批是 ``waiting`` ✓）—— **不阻塞新消息** ✓。
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text

from qzdap_agent_runtime.session.queue import QueueDecision, QueueOutcome
from qzdap_observability.metrics import (
    record_router_queue_depth,
    record_router_seq_snapshot_drift,
)

#: **快路径 + 兜底路径** ✓ 的放行 SQL ✓。
#:
#: ⚠️ **一条语句** ✓ —— 放行与「占用会话执行权」**原子地**一起做 ✓
#: （否则放行成功但执行权没抢到 ✗ —— 两步之间会插进另一轮 ✗✗）。
_RELEASE_SQL = text(
    """
    WITH released AS (
        UPDATE session_turns t
           SET status = 'running',
               started_at = now()
          FROM agent_sessions s
         WHERE t.id = :turn_id
           AND t.tenant_id = :tenant_id
           AND t.session_id = :session_id
           AND t.status = 'queued'
           AND t.ingress_seq IS NOT NULL
           AND s.id = t.session_id
           AND s.tenant_id = :tenant_id
           AND (
                -- ⚠️ **快路径** ✓ —— 快照与权威一致 ✓
                t.ingress_seq = s.last_completed_seq + 1
                -- ⚠️ **兜底路径** ✓ —— 快照落后 ✓（**以权威值为准** ✓：
                -- 终态轮次的最大序号 + 1 就是我 ✓）
                OR t.ingress_seq = COALESCE(
                    (
                        SELECT MAX(done.ingress_seq)
                          FROM session_turns done
                         WHERE done.session_id = t.session_id
                           AND done.status IN ('succeeded', 'failed', 'cancelled')
                           AND done.ingress_seq IS NOT NULL
                    ),
                    0
                ) + 1
           )
           AND NOT EXISTS (
                -- ⚠️ **会话里没有正在跑的轮次** ✓（互斥 ✓ —— 决策 #9 ✓）
                SELECT 1 FROM session_turns running
                 WHERE running.session_id = t.session_id
                   AND running.status = 'running'
           )
        RETURNING t.id, t.session_id, t.ingress_seq
    )
    UPDATE agent_sessions s
       SET current_turn_id = :turn_id,
           updated_at = now()
      FROM released r
     WHERE s.id = r.session_id
       AND s.tenant_id = :tenant_id
    RETURNING s.id
    """
)

#: **兜底路径的快照修复** ✓ —— 把 ``last_completed_seq`` 拉到权威值 ✓。
_REPAIR_SNAPSHOT_SQL = text(
    """
    UPDATE agent_sessions s
       SET last_completed_seq = COALESCE(
               (
                   SELECT MAX(t.ingress_seq)
                     FROM session_turns t
                    WHERE t.session_id = s.id
                      AND t.status = 'succeeded'
                      AND t.ingress_seq IS NOT NULL
               ),
               0
           ),
           updated_at = now()
     WHERE s.id = :session_id
       AND s.tenant_id = :tenant_id
    """
)

#: **快照漂移的判据** ✓ —— 兜底路径命中时用它区分 ✓。
_SNAPSHOT_DRIFT_SQL = text(
    """
    SELECT (
        SELECT COALESCE(s.last_completed_seq, 0)
          FROM agent_sessions s
         WHERE s.id = :session_id
           AND s.tenant_id = :tenant_id
    ) AS snapshot,
    (
        SELECT COALESCE(MAX(done.ingress_seq), 0)
          FROM session_turns done
         WHERE done.session_id = :session_id
           AND done.status IN ('succeeded', 'failed', 'cancelled')
           AND done.ingress_seq IS NOT NULL
    ) AS authority
    """
)

_DEPTH_SQL = text(
    """
    SELECT COUNT(*)
      FROM session_turns t
     WHERE t.session_id = :session_id
       AND t.tenant_id = :tenant_id
       AND t.status = 'queued'
    """
)

_POSITION_SQL = text(
    """
    SELECT COUNT(*)
      FROM session_turns t
     WHERE t.session_id = :session_id
       AND t.tenant_id = :tenant_id
       AND t.status = 'queued'
       AND t.ingress_seq < :ingress_seq
    """
)


class PostgresTurnQueue:
    """同会话的 FIFO 放行 ✓（Router 方案 §4.2 ✓）。"""

    def __init__(self, session: Any) -> None:
        self._s = session

    async def try_release(
        self,
        *,
        tenant_id: UUID,
        session_id: UUID,
        turn_id: UUID,
        ingress_seq: int,
    ) -> QueueDecision:
        """**试一次放行** ✓ —— 成功时轮次已经是 ``running`` ✓。"""
        drift = await self._snapshot_drift(
            tenant_id=tenant_id, session_id=session_id, ingress_seq=ingress_seq
        )
        result = await self._s.execute(
            _RELEASE_SQL,
            {
                "turn_id": turn_id,
                "session_id": session_id,
                "tenant_id": tenant_id,
            },
        )
        released = result.scalar_one_or_none() is not None
        if not released:
            position = await self.queue_position(
                tenant_id=tenant_id, session_id=session_id, ingress_seq=ingress_seq
            )
            return QueueDecision(outcome=QueueOutcome.WAITING, position=position)
        if drift:
            # ⚠️ **快照落后** ✓ —— 走的是兜底路径 ✓ → **修快照** ✓ + **告警** ✓
            record_router_seq_snapshot_drift()
            await self._s.execute(
                _REPAIR_SNAPSHOT_SQL,
                {"session_id": session_id, "tenant_id": tenant_id},
            )
        return QueueDecision(outcome=QueueOutcome.RELEASED, position=1)

    async def queue_depth(self, *, tenant_id: UUID, session_id: UUID) -> int:
        """**当前排队的轮次数** ✓。"""
        result = await self._s.execute(
            _DEPTH_SQL, {"session_id": session_id, "tenant_id": tenant_id}
        )
        depth = int(result.scalar_one_or_none() or 0)
        # ⚠️ **上报排队深度** ✓（Router 方案 §12.2 ✓ —— 只有开关打开时才有 ✓）。
        record_router_queue_depth(tenant_id=str(tenant_id), depth=depth)
        return depth

    async def queue_position(self, *, tenant_id: UUID, session_id: UUID, ingress_seq: int) -> int:
        """**我排在第几个** ✓（1 = 下一个 ✓）。"""
        result = await self._s.execute(
            _POSITION_SQL,
            {
                "session_id": session_id,
                "tenant_id": tenant_id,
                "ingress_seq": ingress_seq,
            },
        )
        return int(result.scalar_one_or_none() or 0) + 1

    async def _snapshot_drift(self, *, tenant_id: UUID, session_id: UUID, ingress_seq: int) -> bool:
        """**快照落后了吗** ✓（快路径不成立但权威值已过 ✓）。"""
        result = await self._s.execute(
            _SNAPSHOT_DRIFT_SQL,
            {
                "session_id": session_id,
                "tenant_id": tenant_id,
                "ingress_seq": ingress_seq,
            },
        )
        row = result.first()
        if row is None:
            return False
        snapshot = int(row[0] or 0)
        authority = int(row[1] or 0)
        # ⚠️ **快照落后 = 快照说的下一个 ≠ 权威说的下一个** ✓（且权威已经
        # 走到我前面了 ✓ —— 否则只是「还没轮到我」✓ 不是漂移 ✓）。
        return snapshot + 1 != authority + 1 and authority + 1 == ingress_seq


__all__ = ["PostgresTurnQueue"]
