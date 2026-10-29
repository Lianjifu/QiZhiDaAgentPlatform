"""``SessionSweeperPort`` 的实现 —— 僵尸轮次 + 幂等键过期。

依据：Session 方案 §3.3（**四类超时** ✓）。

⚠️ **只做两类**：① 僵尸轮次（30 分钟）② 幂等键过期（Gateway 的硬依赖 ✓）。
另两类（审批过期 / 会话空闲）**不在这里做** ——
- 审批过期归**治理域**（`approval_service.expire_if_due` ✓）；
- 会话空闲必须等**「复活」路径**（Stage 2）—— 只关不复活 = 用户的旧对话
  从列表里消失 ✗✗。
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from qzdap_agent_runtime.session.state import (
    TurnStatus,
    assert_turn_transition,
)
from qzdap_agent_runtime.session.sweeper import SweepReport
from sqlalchemy import update

from qzdap.modules.agent_runtime.adapter.persistence.idempotency_store import (
    CLAIM_STALE_MINUTES,
)
from qzdap.modules.agent_runtime.adapter.persistence.models import SessionTurnORM


class PostgresSessionSweeper:
    """清扫器 —— 每类各一次批量操作 ✓。"""

    def __init__(
        self,
        *,
        session_factory: Any,
        idempotency_store: Any,
        batch_limit: int = 1000,
    ) -> None:
        self._sf = session_factory
        self._inbox = idempotency_store
        self._batch_limit = batch_limit

    async def sweep(self, *, now: datetime) -> SweepReport:
        """跑一次清扫 —— **每类独立**，一类失败不影响另一类 ✓。"""
        zombie_turns = await self._sweep_zombie_turns(now=now)
        expired_rows = await self._sweep_expired_idempotency()
        return SweepReport(
            zombie_turns=zombie_turns,
            expired_idempotency_rows=expired_rows,
        )

    async def _sweep_zombie_turns(self, *, now: datetime) -> int:
        """僵尸轮次 —— 卡在 ``running`` 超过 30 分钟的**置 failed** ✓。

        ⚠️ 阈值与幂等守卫的 ``CLAIM_STALE_MINUTES`` **同一个来源** ✓ ——
        两处各写一个数字，迟早会不一致 ✗。

        ⚠️ 转移 ``running → failed`` **由状态机判定** ✓（§4）—— 状态写点
        不自己判断「这个转移合不合法」。
        """
        assert_turn_transition(TurnStatus.RUNNING, TurnStatus.FAILED)
        stale_before = now - timedelta(minutes=CLAIM_STALE_MINUTES)
        async with self._sf.session() as session, session.begin():
            result = await session.execute(
                update(SessionTurnORM)
                .where(
                    SessionTurnORM.status == "running",
                    SessionTurnORM.started_at < stale_before,
                )
                .values(status="failed", error_code="ZOMBIE_TAKEOVER")
            )
            return int(result.rowcount or 0)

    async def _sweep_expired_idempotency(self) -> int:
        """幂等键过期行 —— **Gateway 的硬依赖** ✓（不清会无限膨胀 ✗）。"""
        return await self._inbox.sweep_expired(limit=self._batch_limit)


__all__ = ["PostgresSessionSweeper"]
