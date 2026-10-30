"""**出站队列** —— ``session_events`` 上的 outbox 实现（真库）。

依据：Session 方案 §7（事件落库与 outbox）、§10（表终态）。

⚠️ **队列 = ``session_events`` 里的一个子集**（按 ``event_type`` 过滤 ✓）：
那张表同时是**事件日志**（每个 chunk 一行，供重放 ✓）—— 若 worker 把
``message`` / ``usage`` / ``done`` 这些 chunk 事件也当成「待投递的消息」，
就会把 web 的 chunk 投到 IM 渠道 ✗✗（重复投递）。

所以：**只有 ``im_reply`` 那一类行进队列** ✓（渠道出站 ✓），
chunk 事件仍由轮次收尾统一标 delivered ✓（``journal.mark_delivered``）。

⚠️ **自持事务、立即提交** ✓ —— 入队必须**先于**投递落库 ✓（投递失败时
这一行还在 → worker 能重试 ✓；这正是事务性 outbox 的全部要点 ✓）。
"""

from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID

from qzdap_agent_runtime.outbox import (
    IM_REPLY_EVENT_TYPE,
    MAX_DELIVERY_ATTEMPTS,
    OutboundMessage,
    OutboxEvent,
)
from sqlalchemy import delete, func, select, text, update

from qzdap.modules.agent_runtime.adapter.persistence.models import SessionEventORM

_log = logging.getLogger("qzdap.agent_runtime.outbox")


class PostgresOutboxRepository:
    """``OutboxRepository`` 的生产实现 ✓。"""

    def __init__(
        self,
        session_factory: Any,
        *,
        event_types: tuple[str, ...] = (IM_REPLY_EVENT_TYPE,),
    ) -> None:
        self._sf = session_factory
        # 队列只管**自己那几类**事件 ✓（chunk 事件是日志，不是队列 ✗）。
        self._event_types = event_types

    # ── 入队 ───────────────────────────────────────────────────────────

    async def enqueue(
        self, *, turn_id: str, event_type: str, payload: dict[str, Any]
    ) -> OutboundMessage:
        """入队一条出站消息 —— seq 在**轮次内**递增 ✓。"""
        turn_uuid = UUID(str(turn_id))
        async with self._sf.session() as session, session.begin():
            next_seq = await session.scalar(
                select(func.coalesce(func.max(SessionEventORM.seq), 0) + 1).where(
                    SessionEventORM.turn_id == turn_uuid
                )
            )
            seq = int(next_seq or 1)
            session.add(
                SessionEventORM(
                    turn_id=turn_uuid,
                    seq=seq,
                    event_type=event_type[:64],
                    payload=dict(payload),
                    delivery_status="pending",
                    delivery_attempts=0,
                )
            )
        return OutboundMessage(turn_id=str(turn_id), seq=seq, event_type=event_type)

    # ── 取件 ───────────────────────────────────────────────────────────

    async def list_pending(self, limit: int = 100) -> list[OutboxEvent]:
        """待投递的消息 ✓（按创建时间、seq 升序 ✓ —— 先到先投 ✓）。"""
        async with self._sf.session() as session:
            result = await session.execute(
                select(SessionEventORM)
                .where(
                    SessionEventORM.event_type.in_(self._event_types),
                    SessionEventORM.delivery_status.in_(("pending", "failed")),
                    SessionEventORM.delivery_attempts < MAX_DELIVERY_ATTEMPTS,
                )
                .order_by(SessionEventORM.created_at, SessionEventORM.seq)
                .limit(limit)
            )
            rows = result.scalars().all()
        return [
            OutboxEvent(
                turn_id=str(row.turn_id),
                seq=row.seq,
                event_type=row.event_type,
                payload=dict(row.payload or {}),
                delivery_status=row.delivery_status,
                delivery_attempts=row.delivery_attempts,
                delivered_at=row.delivered_at,
                created_at=row.created_at,
            )
            for row in rows
        ]

    # ── 回写状态 ───────────────────────────────────────────────────────

    async def mark_delivered(self, turn_id: str, seq: int) -> None:
        """投递成功 ✓ —— 键被消费（这一行不再被 worker 取到 ✓）。"""
        async with self._sf.session() as session, session.begin():
            await session.execute(
                update(SessionEventORM)
                .where(
                    SessionEventORM.turn_id == UUID(str(turn_id)),
                    SessionEventORM.seq == seq,
                )
                .values(delivery_status="delivered", delivered_at=func.now())
            )

    async def mark_failed(
        self, turn_id: str, seq: int, attempts: int, last_error: str
    ) -> None:
        """投递失败 —— 记次数 ✓（worker 下一轮还会取它 ✓）。

        ⚠️ **最后一次错误**写进 payload ✓ —— 死信表只记最后一次 ✓，
        但运维先看到的是队列里的这一行 ✓。
        """
        uuid_turn = UUID(str(turn_id))
        async with self._sf.session() as session, session.begin():
            row = (
                await session.execute(
                    select(SessionEventORM).where(
                        SessionEventORM.turn_id == uuid_turn,
                        SessionEventORM.seq == seq,
                    )
                )
            ).scalar_one_or_none()
            if row is None:
                return
            payload = dict(row.payload or {})
            payload["_last_error"] = last_error[:2000]
            await session.execute(
                update(SessionEventORM)
                .where(
                    SessionEventORM.turn_id == uuid_turn,
                    SessionEventORM.seq == seq,
                )
                .values(
                    delivery_status="failed",
                    delivery_attempts=attempts,
                    payload=payload,
                )
            )

    async def move_to_dead_letter(
        self, turn_id: str, seq: int, attempts: int, last_error: str
    ) -> None:
        """超了最大次数 → **进死信表** ✓（原行删掉 ✓ —— 死信表才是它的归宿 ✓）。"""
        uuid_turn = UUID(str(turn_id))
        async with self._sf.session() as session, session.begin():
            row = (
                await session.execute(
                    select(SessionEventORM).where(
                        SessionEventORM.turn_id == uuid_turn,
                        SessionEventORM.seq == seq,
                    )
                )
            ).scalar_one_or_none()
            if row is None:
                return
            await session.execute(
                text(
                    "INSERT INTO outbox_dead_letters "
                    "(turn_id, seq, attempt, event_type, payload, last_error) "
                    "VALUES (:turn_id, :seq, :attempt, :event_type, "
                    "CAST(:payload AS jsonb), :last_error)"
                ),
                {
                    "turn_id": uuid_turn,
                    "seq": seq,
                    "attempt": attempts,
                    "event_type": row.event_type,
                    "payload": json.dumps(dict(row.payload or {}), default=str),
                    "last_error": last_error[:4000],
                },
            )
            await session.execute(
                delete(SessionEventORM).where(
                    SessionEventORM.turn_id == uuid_turn,
                    SessionEventORM.seq == seq,
                )
            )
        _log.warning(
            "outbox dead-letter: turn_id=%s seq=%s attempts=%s error=%s",
            turn_id,
            seq,
            attempts,
            last_error,
        )


__all__ = ["PostgresOutboxRepository"]
