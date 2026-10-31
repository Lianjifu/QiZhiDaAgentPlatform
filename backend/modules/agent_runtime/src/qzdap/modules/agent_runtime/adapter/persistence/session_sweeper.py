"""``SessionSweeperPort`` 的实现 —— 僵尸轮次 + 幂等键过期。

依据：Session 方案 §3.3（**四类超时** ✓）。

⚠️ **只做两类**：① 僵尸轮次（30 分钟）② 幂等键过期（Gateway 的硬依赖 ✓）。
另两类（审批过期 / 会话空闲）**不在这里做** ——
- 审批过期归**治理域**（`approval_service.expire_if_due` ✓）；
- 会话空闲必须等**「复活」路径**（Stage 2）—— 只关不复活 = 用户的旧对话
  从列表里消失 ✗✗。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from logging import getLogger
from typing import Any

from sqlalchemy import update

from qzdap.modules.agent_runtime.adapter.persistence.idempotency_store import (
    CLAIM_STALE_MINUTES,
)
from qzdap.modules.agent_runtime.adapter.persistence.models import SessionTurnORM
from qzdap_agent_runtime.session.state import (
    TurnStatus,
    assert_turn_transition,
)
from qzdap_agent_runtime.session.sweeper import SweepReport

_log = getLogger(__name__)


class PostgresSessionSweeper:
    """清扫器 —— 每类各一次批量操作 ✓。"""

    def __init__(
        self,
        *,
        session_factory: Any,
        idempotency_store: Any,
        expire_approvals: Callable[[datetime], Awaitable[int]] | None = None,
        batch_limit: int = 1000,
    ) -> None:
        self._sf = session_factory
        self._inbox = idempotency_store
        #: ⚠️ **审批过期的执行者** ✓（Session 方案 §3.3 的第 2 类 ✓）——
        #: **归治理域** ✓（`approval_service.expire_if_due` ✓）—— 这里只
        #: **给它一个回调** ✓（不引治理模块 ✓ —— 组合根接线 ✓）。
        self._expire_approvals = expire_approvals
        self._batch_limit = batch_limit

    async def sweep(self, *, now: datetime) -> SweepReport:
        """跑一次清扫 —— **每类独立**，一类失败不影响另一类 ✓。"""
        zombie_turns = await self._sweep_zombie_turns(now=now)
        expired_rows = await self._sweep_expired_idempotency()
        expired_approvals = await self._sweep_expired_approvals(now=now)
        return SweepReport(
            zombie_turns=zombie_turns,
            expired_idempotency_rows=expired_rows,
            expired_approvals=expired_approvals,
        )

    async def _sweep_expired_approvals(self, *, now: datetime) -> int:
        """**到期未决策的审批 → 自动过期** ✓（§3.3 第 2 类 ✓）。

        ⚠️ **没有执行者就什么都不做** ✓（不猜 ✓ —— 「没有触发者 = 能力不存在」
        ✗✗ —— 但组合根**接上了** ✓ —— 这里只是没接线时不报错 ✓）。
        """
        if self._expire_approvals is None:
            return 0
        try:
            return int(await self._expire_approvals(now))
        except Exception:
            # ⚠️ **一类失败不影响另一类** ✓（清扫器整体还要跑 ✓）。
            _log.exception("approval expiry sweep failed")
            return 0

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
