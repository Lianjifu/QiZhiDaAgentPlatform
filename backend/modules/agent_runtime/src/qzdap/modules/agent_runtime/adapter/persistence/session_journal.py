"""新架构的轮次 + 事件日志 —— ``session_turns`` / ``session_events``。

依据：``docs/refactor/session-architecture/gateway-refactor-plan.md`` §10
Stage 4b（无感重放）、§4.5；``session-refactor-plan.md`` §7（事件落库与 outbox）。

**这一层是 Session 侧对 Gateway 的硬交付**（Gateway 方案 §4.5 的前置依赖）：
重放要成立，必须「**真的写、真的读**``session_events``」。

两件事：

1. **轮次双写**（``session_turns``）—— 新表与旧的 ``agent_turns`` 并存写入
   （Session 方案 §12 的双写期）。除了当权威轮次表，它还是
   ``session_events`` 的**外键父行** —— 事件行必须挂在一个存在的轮次上。
2. **事件落库**（``session_events``）—— **每个 chunk 一行**，``seq`` 在轮次内
   严格递增。落库**先于投递**（§7）：chunk 写进去再交给 SSE 编码器。

⚠️ **每次写都自持事务并立即提交** —— 事件必须在「投递」之前落库，否则断线
重连时读不到已发出的那一段。

⚠️ **读必须按租户过滤**：``session_events`` 表**没有** ``tenant_id`` 列
（主键是 ``(turn_id, seq)``），事件行的租户归属由它的**轮次**决定 → 读
事件要 JOIN ``session_turns`` 并按 ``tenant_id`` 过滤。
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from qzdap_agent_runtime.gateway.replay import StoredEvent
from sqlalchemy import func, select, text, update
from sqlalchemy.exc import IntegrityError

from qzdap.modules.agent_runtime.adapter.persistence.idempotency_store import (
    CLAIM_STALE_MINUTES,
)
from qzdap.modules.agent_runtime.adapter.persistence.models import (
    SessionEventORM,
    SessionTurnORM,
)

_log = logging.getLogger(__name__)

#: 轮次的终态 —— 重放时用它判断「这一轮结束了没有」。
FINISHED_STATUSES = ("succeeded", "failed", "cancelled")


class PostgresSessionJournal:
    """``session_turns`` + ``session_events`` 的读写。

    **一次写一个事务**（写入即提交）—— 事件必须在投递前落库。
    """

    def __init__(self, session_factory: Any) -> None:
        self._sf = session_factory

    # ── 轮次 ───────────────────────────────────────────────────────────

    async def start_turn(
        self,
        *,
        turn_id: UUID,
        tenant_id: UUID,
        workspace_id: UUID,
        session_id: UUID,
        idempotency_key: str,
        key_strength: str,
        agent_version: str,
        model_version: str,
        trace_id: str | None = None,
        route_decision: dict[str, Any] | None = None,
    ) -> None:
        """写一行轮次 —— 状态 ``running``（在飞）。

        这是 ``session_events`` 的**外键父行**，必须先于事件写入。

        ⚠️ **撞键的处理**：同一会话里**另一个在飞的同键轮次**会让唯一索引
        （``uq_session_turns_session_idem_strong``）拒绝这一行。正常情况下
        幂等守卫的原子 claim 只放一个进来，因此撞键多半是**僵尸**（进程死了，
        状态没落终态）—— 那就把僵尸落到终态再插一次（阈值与守卫的
        ``CLAIM_STALE_MINUTES`` **同一个来源**）。**年轻的撞键行照旧报错**
        —— 那是真的重复执行，必须被挡住。
        """
        row = SessionTurnORM(
            id=turn_id,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            session_id=session_id,
            idempotency_key=idempotency_key,
            key_strength=key_strength,
            status="running",
            agent_version=agent_version,
            model_version=model_version,
            trace_id=(trace_id or None) and trace_id[:64],
            # 路由决策留痕 —— **产出者是 Router**（本层只代填）。
            route_decision=route_decision,
        )
        try:
            await self._insert_turn(row)
        except IntegrityError:
            if not await self._retire_zombie(
                session_id=session_id,
                idempotency_key=idempotency_key,
            ):
                raise
            await self._insert_turn(row)

    async def _insert_turn(self, row: SessionTurnORM) -> None:
        async with self._sf.session() as session, session.begin():
            session.add(row)

    async def _retire_zombie(
        self, *, session_id: UUID, idempotency_key: str
    ) -> bool:
        """把「同会话、同键、且已经僵了很久」的在飞轮次落到终态。

        返回 True = 确实清掉了一行僵尸（可以重试插入）；False = 撞键的是
        **年轻的**在飞轮次（真的重复执行）→ **不碰**，让调用方撞到 IntegrityError。
        """
        async with self._sf.session() as session, session.begin():
            result = await session.execute(
                update(SessionTurnORM)
                .where(
                    SessionTurnORM.session_id == session_id,
                    SessionTurnORM.idempotency_key == idempotency_key,
                    SessionTurnORM.key_strength == "strong",
                    SessionTurnORM.status.in_(("queued", "running", "waiting")),
                    SessionTurnORM.started_at
                    < func.now() - text(f"INTERVAL '{CLAIM_STALE_MINUTES} minutes'"),
                )
                .values(status="failed", error_code="ZOMBIE_TAKEOVER")
            )
            return bool(result.rowcount)

    async def finish_turn(
        self,
        *,
        turn_id: UUID,
        status: str,
        error_code: str | None = None,
        cost_usd: float | None = None,
    ) -> None:
        """把轮次落到终态 —— 重放时用它判断「这一轮结束了没有」。"""
        if status not in FINISHED_STATUSES:
            raise ValueError(f"not a terminal turn status: {status}")
        async with self._sf.session() as session, session.begin():
            await session.execute(
                update(SessionTurnORM)
                .where(SessionTurnORM.id == turn_id)
                .values(
                    status=status,
                    error_code=error_code,
                    cost_usd=cost_usd,
                    finished_at=func.now(),
                )
            )

    async def get_turn_status(self, turn_id: UUID, *, tenant_id: UUID) -> str | None:
        """读轮次状态；轮次不存在或不属于该租户 → ``None``。"""
        async with self._sf.session() as session:
            result = await session.execute(
                select(SessionTurnORM.status).where(
                    SessionTurnORM.id == turn_id,
                    SessionTurnORM.tenant_id == tenant_id,
                )
            )
            return result.scalar_one_or_none()

    # ── 事件 ───────────────────────────────────────────────────────────

    async def append_event(
        self,
        *,
        turn_id: UUID,
        seq: int,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        """写一条事件 —— **落库先于投递**（§7）。"""
        async with self._sf.session() as session, session.begin():
            session.add(
                SessionEventORM(
                    turn_id=turn_id,
                    seq=seq,
                    event_type=event_type[:64],
                    payload=payload,
                    delivery_status="pending",
                )
            )

    async def mark_delivered(self, *, turn_id: UUID) -> None:
        """把这一轮还挂着的 ``pending`` 事件标成 ``delivered``。

        web 的「投递」就是把 chunk 交给 SSE 编码器；轮次正常收尾时统一标记。
        """
        async with self._sf.session() as session, session.begin():
            await session.execute(
                update(SessionEventORM)
                .where(
                    SessionEventORM.turn_id == turn_id,
                    SessionEventORM.delivery_status == "pending",
                )
                .values(delivery_status="delivered", delivered_at=func.now())
            )

    async def get_events(
        self, turn_id: UUID, *, tenant_id: UUID, after_seq: int = 0
    ) -> list[StoredEvent]:
        """读出 ``seq > after_seq`` 的事件，按 seq 升序。

        ⚠️ **必须 JOIN 轮次表按租户过滤** —— 事件表自己没有 ``tenant_id``。
        """
        async with self._sf.session() as session:
            result = await session.execute(
                select(SessionEventORM)
                .join(SessionTurnORM, SessionTurnORM.id == SessionEventORM.turn_id)
                .where(
                    SessionEventORM.turn_id == turn_id,
                    SessionTurnORM.tenant_id == tenant_id,
                    SessionEventORM.seq > after_seq,
                )
                .order_by(SessionEventORM.seq.asc())
            )
            return [
                StoredEvent(
                    seq=row.seq,
                    event_type=row.event_type,
                    payload=dict(row.payload or {}),
                )
                for row in result.scalars().all()
            ]


__all__ = ["FINISHED_STATUSES", "PostgresSessionJournal"]
