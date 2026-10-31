"""``SessionSweeperPort`` 的实现 —— 僵尸轮次 + 审批过期 + 会话空闲 + 幂等键过期。

依据：Session 方案 §3.3（**四类超时** ✓）。

⚠️ **四类都做** ✓：
① 僵尸轮次（30 分钟 ✓）② 审批过期（15 分钟 ✓ —— 判定归治理域 ✓）
③ 会话空闲（30 天 ✓ —— **只关「有复活路径」的** ✓）④ 幂等键过期
（Gateway 的硬依赖 ✓）。
⚠️ **会话空闲的前置是「复活」路径** ✓（方案 §3.4 ✓）—— 只关不复活 =
用户的旧对话从列表里消失 ✗✗ → **复活 = 新建一个会话接管** ✓（旧行释放
外部会话键 ✓ —— 部分唯一索引 ✓）。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from logging import getLogger
from typing import Any

from sqlalchemy import delete, func, select, update

from qzdap.modules.agent_runtime.adapter.persistence.idempotency_store import (
    CLAIM_STALE_MINUTES,
)
from qzdap.modules.agent_runtime.adapter.persistence.models import (
    SessionEventORM,
    SessionORM,
    SessionTurnORM,
)
from qzdap.modules.agent_runtime.adapter.persistence.session_store import (
    PostgresSessionStore,
)
from qzdap_agent_runtime.session.manager import CloseReason
from qzdap_agent_runtime.session.state import (
    TurnStatus,
    plan_turn_transition,
)
from qzdap_agent_runtime.session.sweeper import SweepReport
from qzdap_kernel.error_codes import ErrorCode

_log = getLogger(__name__)

#: 会话空闲的默认阈值（天）✓ —— 决策 #7 ✓（30 天 ✓ —— 可配 ✓）。
DEFAULT_IDLE_TIMEOUT_DAYS = 30

#: **事件流保留期**（天）✓ —— 默认 7 天 ✓（可配 ✓）。
DEFAULT_EVENT_RETENTION_DAYS = 7


class PostgresSessionSweeper:
    """清扫器 —— 每类各一次批量操作 ✓。"""

    def __init__(
        self,
        *,
        session_factory: Any,
        idempotency_store: Any,
        expire_approvals: Callable[[datetime], Awaitable[int]] | None = None,
        batch_limit: int = 1000,
        idle_timeout_days: int = DEFAULT_IDLE_TIMEOUT_DAYS,
        event_retention_days: int = DEFAULT_EVENT_RETENTION_DAYS,
    ) -> None:
        self._sf = session_factory
        self._inbox = idempotency_store
        #: ⚠️ **审批过期的执行者** ✓（Session 方案 §3.3 的第 2 类 ✓）——
        #: **归治理域** ✓（`approval_service.expire_if_due` ✓）—— 这里只
        #: **给它一个回调** ✓（不引治理模块 ✓ —— 组合根接线 ✓）。
        self._expire_approvals = expire_approvals
        self._batch_limit = batch_limit
        #: ⚠️ **会话空闲阈值（天）** ✓ —— 决策 #7 ✓（30 天 ✓ —— 可配 ✓）。
        self._idle_timeout_days = max(1, int(idle_timeout_days))
        #: ⚠️ **事件流保留期（天）** ✓ —— 默认 7 天 ✓（可配 ✓）。
        self._event_retention_days = max(1, int(event_retention_days))

    async def sweep(self, *, now: datetime) -> SweepReport:
        """跑一次清扫 —— **每类独立**，一类失败不影响另一类 ✓。"""
        zombie_turns = await self._sweep_zombie_turns(now=now)
        expired_rows = await self._sweep_expired_idempotency()
        expired_approvals = await self._sweep_expired_approvals(now=now)
        idle_sessions = await self._sweep_idle_sessions(now=now)
        expired_events = await self._sweep_expired_events(now=now)
        return SweepReport(
            zombie_turns=zombie_turns,
            expired_idempotency_rows=expired_rows,
            expired_approvals=expired_approvals,
            idle_sessions=idle_sessions,
            expired_events=expired_events,
        )

    async def _sweep_expired_events(self, *, now: datetime) -> int:
        """**过了保留期的事件行 → 删掉** ✓。

        ⚠️ **只删「已结束」的轮次的事件** ✓ —— 还在跑的轮次 ✓ / 还在等审批的
        轮次 ✓（可能被恢复 ✓ —— 恢复要重放事件 ✓）**一律不动** ✓。
        ⚠️ **删事件不丢轮次** ✓ —— 轮次的终态在 ``session_turns`` ✓ ——
        事件流只是**重放日志** ✓（断线重连用 ✓）。
        """
        cutoff = now - timedelta(days=self._event_retention_days)
        try:
            async with self._sf.session() as session, session.begin():
                result = await session.execute(
                    delete(SessionEventORM).where(
                        SessionEventORM.turn_id.in_(
                            select(SessionTurnORM.id).where(
                                SessionTurnORM.status.in_(["succeeded", "failed", "cancelled"]),
                                SessionTurnORM.finished_at.isnot(None),
                                SessionTurnORM.finished_at < cutoff,
                            )
                        ),
                    )
                )
                return int(result.rowcount or 0)
        except Exception:
            # ⚠️ **一类失败不影响另一类** ✓（清扫器整体还要跑 ✓）。
            _log.exception("event retention sweep failed")
            return 0

    async def _sweep_idle_sessions(self, *, now: datetime) -> int:
        """**空闲超时的会话 → 关闭** ✓（方案 §3.3 的第 3 类 ✓）。

        ⚠️ **「最后活动」= 最后一轮的开始时间** ✓ —— 不是会话行的
        ``updated_at`` ✓（那列会被摘要写入之类的动作顶上去 ✗）。
        ⚠️ **只关「有外部会话键」的** ✓ —— 那些**有复活路径** ✓（方案 §3.4
        ✓：用户「隔了一周再问一句」→ 新会话接管 ✓ → 不报错 ✓）。
        ⚠️ **Web 会话不关** ✓ —— 它没有复活路径 ✓ → 关了就是「用户的旧
        对话从列表里消失」✗✗（方案 §3.4 点名的坑 ✓）。
        """
        idle_before = now - timedelta(days=self._idle_timeout_days)
        last_activity = (
            select(func.max(SessionTurnORM.started_at))
            .where(SessionTurnORM.session_id == SessionORM.id)
            .correlate(SessionORM)
            .scalar_subquery()
        )
        async with self._sf.session() as session:
            rows = (
                await session.execute(
                    select(SessionORM.id, SessionORM.tenant_id)
                    .where(
                        SessionORM.status == "open",
                        SessionORM.channel_session_key.isnot(None),
                        func.coalesce(last_activity, SessionORM.created_at) < idle_before,
                    )
                    .limit(self._batch_limit)
                )
            ).all()
            if not rows:
                return 0
            store = PostgresSessionStore(session)
            closed = 0
            for session_id, tenant_id in rows:
                # ⚠️ **走仓储的关闭口** ✓ —— 关闭原因要落库 ✓
                # （``metadata["close_reason"]`` ✓ —— 之前 reason 被丢掉了 ✗✗）。
                await store.close_session(
                    session_id=session_id,
                    tenant_id=tenant_id,
                    reason=CloseReason.IDLE_TIMEOUT,
                )
                closed += 1
            return closed

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
        target = plan_turn_transition(TurnStatus.RUNNING, TurnStatus.FAILED)
        assert target is not None
        stale_before = now - timedelta(minutes=CLAIM_STALE_MINUTES)
        async with self._sf.session() as session, session.begin():
            result = await session.execute(
                update(SessionTurnORM)
                .where(
                    SessionTurnORM.status == TurnStatus.RUNNING.value,
                    SessionTurnORM.started_at < stale_before,
                )
                .values(
                    status=target,
                    error_code=ErrorCode.ZOMBIE_TAKEOVER.value,
                    finished_at=func.now(),
                )
            )
            return int(result.rowcount or 0)

    async def _sweep_expired_idempotency(self) -> int:
        """幂等键过期行 —— **Gateway 的硬依赖** ✓（不清会无限膨胀 ✗）。"""
        return await self._inbox.sweep_expired(limit=self._batch_limit)


__all__ = ["PostgresSessionSweeper"]
