"""新架构的轮次 + 事件日志 —— ``session_turns`` / ``session_events``。

依据：``docs/refactor/session-architecture/gateway-refactor-plan.md`` §10
Stage 4b（无感重放）、§4.5；``session-refactor-plan.md`` §7（事件落库与 outbox）。

**这一层是 Session 侧对 Gateway 的硬交付**（Gateway 方案 §4.5 的前置依赖）：
重放要成立，必须「**真的写、真的读**``session_events``」。

两件事：

1. **轮次落库**（``session_turns``）—— 它是**权威轮次表** ✓（旧表
   ``agent_turns`` 已停写 · S-15b ✓），同时是 ``session_events`` 的
   **外键父行** —— 事件行必须挂在一个存在的轮次上 ✓。
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

from sqlalchemy import func, select, text, update
from sqlalchemy.exc import IntegrityError

from qzdap.modules.agent_runtime.adapter.persistence.idempotency_store import (
    CLAIM_STALE_MINUTES,
)
from qzdap.modules.agent_runtime.adapter.persistence.models import (
    SessionEventORM,
    SessionTurnORM,
)
from qzdap_agent_runtime.gateway.replay import StoredEvent

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
        user_input: str | None = None,
        trace_id: str | None = None,
        route_decision: dict[str, Any] | None = None,
        ingress_seq: int | None = None,
    ) -> None:
        """写一行轮次 —— 状态 ``running``（在飞）/ ``queued``（排队中 ✓）。

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
            # ⚠️ **排队中的轮次落 ``queued``** ✓（Router 方案 §4.2 ✓）——
            # 放行时**原子地**改成 ``running`` ✓（决策 #9 ✓ —— 唯一权威 ✓）。
            status="queued" if ingress_seq is not None else "running",
            # ⚠️ **入站序号** ✓（FIFO 的排序依据 ✓）。
            ingress_seq=ingress_seq,
            agent_version=agent_version,
            model_version=model_version,
            # 这一轮用户说了什么 ✓（停旧写之后，任务卡片只能从这里取 ✓）。
            user_input=user_input,
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

    async def _retire_zombie(self, *, session_id: UUID, idempotency_key: str) -> bool:
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
        """把轮次落到终态 —— 重放时用它判断「这一轮结束了没有」。

        ⚠️ **同事务更新会话的入站序号快照** ✓（Router 方案 §4.2 ✓）——
        轮次终态与会话行 ``last_completed_seq`` **一起落** ✓ → 正常路径上
        **不一致窗口 = 0** ✓（不一致 → 兜底路径 ✓ + 告警 ✓）。
        """
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
            # ⚠️ **快照推进** ✓ —— **任何终态都推进** ✓（失败的那一轮也推进 ✓
            # —— 否则队列会卡在失败那一轮 ✗✗）。
            await session.execute(
                text(
                    """
                    UPDATE agent_sessions s
                       SET last_completed_seq = t.ingress_seq
                      FROM session_turns t
                     WHERE t.id = :turn_id
                       AND t.session_id = s.id
                       AND t.ingress_seq IS NOT NULL
                       AND s.last_completed_seq < t.ingress_seq
                    """
                ),
                {"turn_id": turn_id},
            )

    async def write_pending_approval(self, *, turn_id: UUID, pending: dict[str, Any]) -> None:
        """轮次挂起等审批 —— **挂起信息落库** ✓（Session 方案 §8 · 决策 #6）。

        ⚠️ 同时把轮次状态置 ``waiting`` —— 「这一轮在等审批」这件事
        **由轮次表说了算** ✓（会话那一列只是给人看的 ✓）。
        """
        async with self._sf.session() as session, session.begin():
            await session.execute(
                update(SessionTurnORM)
                .where(SessionTurnORM.id == turn_id)
                .values(pending_approval=pending, status="waiting")
            )

    async def find_pending_approval(
        self, *, session_id: UUID, tenant_id: UUID
    ) -> tuple[UUID, dict[str, Any]] | None:
        """查这个会话**正在等审批**的那一轮 + 它的挂起信息 ✓。

        ⚠️ 取**最近**的一个（多个挂起时以最新的为准 ✓）——
        审批恢复路径靠它校验「挂起的是哪个工具、参数有没有被改」✓。
        """
        async with self._sf.session() as session:
            result = await session.execute(
                select(SessionTurnORM.id, SessionTurnORM.pending_approval)
                .where(
                    SessionTurnORM.session_id == session_id,
                    SessionTurnORM.tenant_id == tenant_id,
                    SessionTurnORM.status == "waiting",
                    SessionTurnORM.pending_approval.isnot(None),
                )
                .order_by(SessionTurnORM.started_at.desc())
                .limit(1)
            )
            row = result.first()
            if row is None or row[1] is None:
                return None
            return row[0], dict(row[1])

    async def list_waiting_approval_sessions(self, *, tenant_id: UUID) -> set[UUID]:
        """哪些会话**正在等审批** ✓（一次查询，别按会话逐个查 ✗）。

        ⚠️ 会话列表 / 任务列表要用它判断「等你确认」—— 那一列
        ``wait_status`` **已退役**（台账 X6 ✅），权威是**轮次表** ✓。
        """
        async with self._sf.session() as session:
            result = await session.execute(
                select(SessionTurnORM.session_id).where(
                    SessionTurnORM.tenant_id == tenant_id,
                    SessionTurnORM.status == "waiting",
                    SessionTurnORM.pending_approval.isnot(None),
                )
            )
            return {row[0] for row in result.all()}

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

    async def record_agent_decision(self, *, turn_id: UUID, decision: dict[str, Any]) -> None:
        """**写 `session_turns.agent_decision`** ✓（轮次级快照 ✓ —— 最后一个专家 ✓）。

        ⚠️ **只写「用了什么」** ✓（专家 id ✓ / 版本 ✓ / 解析出的模型与工具 ✓）——
        **不写「为什么挑了它」** ✓（理由会变 ✓ 用法是事实 ✓）。
        """
        async with self._sf.session() as session, session.begin():
            await session.execute(
                update(SessionTurnORM)
                .where(SessionTurnORM.id == turn_id)
                .values(agent_decision=decision, updated_at=func.now())
            )

    async def next_event_seq(self, *, turn_id: UUID) -> int:
        """**这一轮的下一个事件序号** ✓（轮次内严格递增 ✓）。"""
        async with self._sf.session() as session:
            result = await session.execute(
                select(func.coalesce(func.max(SessionEventORM.seq), 0)).where(
                    SessionEventORM.turn_id == turn_id
                )
            )
            return int(result.scalar_one() or 0) + 1

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
