"""``TurnClaimPort`` 的 SQL 实现 —— 会话执行权的**原子占用**。

依据：Session 方案 §4.4 / §6（``current_turn_id`` + ``session_turns.status``
推导 ✓）。

⚠️ **为什么用 ``text()`` 而不是 ORM**：claim 的条件要**关联子查询**
（``current_turn_id`` 指向的轮次是不是终态/僵尸）—— UPDATE 的目标表与子查询
的关联用 ORM 表达很别扭，raw SQL 更直白 ✓（与 ``idempotency_store`` 的做法
一致）。

⚠️ **僵尸阈值复用同一个来源**（``CLAIM_STALE_MINUTES``）—— 与幂等守卫、
sweeper 三处同源 ✓。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from qzdap_agent_runtime.session.state import TurnStatus
from sqlalchemy import text

from qzdap.modules.agent_runtime.adapter.persistence.idempotency_store import (
    CLAIM_STALE_MINUTES,
)

#: 占用执行权 —— 会话行上的原子 CAS ✓。
_CLAIM_SQL = text(
    """
    UPDATE agent_sessions s
       SET current_turn_id = :turn_id,
           updated_at = now()
     WHERE s.id = :session_id
       AND s.tenant_id = :tenant_id
       AND (
            s.current_turn_id IS NULL
            OR EXISTS (
                SELECT 1 FROM session_turns t
                 WHERE t.id = s.current_turn_id
                   AND (
                        t.status IN ('succeeded', 'failed', 'cancelled')
                        OR t.started_at < :stale_before
                   )
            )
            OR (
                NOT EXISTS (
                    SELECT 1 FROM session_turns t2 WHERE t2.id = s.current_turn_id
                )
                AND s.updated_at < :stale_before
            )
       )
    RETURNING s.current_turn_id
    """
)

_RELEASE_SQL = text(
    """
    UPDATE agent_sessions
       SET current_turn_id = NULL,
           updated_at = now()
     WHERE id = :session_id
       AND tenant_id = :tenant_id
       AND current_turn_id = :turn_id
    """
)

_CURRENT_STATUS_SQL = text(
    """
    SELECT t.status
      FROM session_turns t
     WHERE t.id = (
               SELECT s.current_turn_id
                 FROM agent_sessions s
                WHERE s.id = :session_id
                  AND s.tenant_id = :tenant_id
           )
    """
)


class PostgresTurnClaim:
    """会话执行权 —— 轮次表是唯一权威 ✓。"""

    def __init__(self, session: Any) -> None:
        self._s = session

    async def claim(
        self, *, tenant_id: UUID, session_id: UUID, turn_id: UUID
    ) -> bool:
        """占用执行权 —— 已被占用（且不是僵尸）返回 ``False`` ✓。"""
        stale_before = datetime.now(UTC) - timedelta(minutes=CLAIM_STALE_MINUTES)
        result = await self._s.execute(
            _CLAIM_SQL,
            {
                "turn_id": turn_id,
                "session_id": session_id,
                "tenant_id": tenant_id,
                "stale_before": stale_before,
            },
        )
        return result.scalar_one_or_none() is not None

    async def release(
        self, *, tenant_id: UUID, session_id: UUID, turn_id: UUID
    ) -> None:
        """释放执行权 —— **只释放自己占的那个** ✓。"""
        await self._s.execute(
            _RELEASE_SQL,
            {
                "turn_id": turn_id,
                "session_id": session_id,
                "tenant_id": tenant_id,
            },
        )

    async def current_turn_status(
        self, *, tenant_id: UUID, session_id: UUID
    ) -> TurnStatus | None:
        """当前轮次的状态 —— 没有在飞的轮次就是 ``None`` ✓。"""
        result = await self._s.execute(
            _CURRENT_STATUS_SQL,
            {"session_id": session_id, "tenant_id": tenant_id},
        )
        raw = result.scalar_one_or_none()
        if raw is None:
            return None
        try:
            return TurnStatus(str(raw))
        except ValueError:  # pragma: no cover - 表里有表外取值
            return None


__all__ = ["PostgresTurnClaim"]
