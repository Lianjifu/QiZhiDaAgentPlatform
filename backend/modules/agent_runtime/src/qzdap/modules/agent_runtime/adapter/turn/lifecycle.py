"""``TurnLifecyclePort`` 的实现 —— 轮次行 + 事件流 + 轮次终态。

依据：Session 方案 §6 / §7（唯一 turn 实现的治理语义 ✓）。

⚠️ **轮次只写新表** ``session_turns`` ✓（``SessionJournal``）—— 旧轮次表
已退役（停写 S-15b ✓ → 删表迁移 0062 ✓），**事件流的外键父行**也是它 ✓。

⚠️ **落库先于投递**：事件必须挂在一个**已存在**的轮次上 ✓ ——
``start_turn`` 先落轮次行，``append_event`` 才写得到 ✓。
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any
from uuid import UUID

from qzdap.modules.agent_runtime.application.ports import (
    EventPublisher,
    SessionJournal,
)
from qzdap.modules.agent_runtime.domain import Turn
from qzdap_agent_runtime.session.state import TurnStatus
from qzdap_agent_runtime.session.turn_runner import TurnLifecyclePort, TurnRequest
from qzdap_kernel.ids import SessionId, TenantId, TurnId, WorkspaceId

_log = logging.getLogger(__name__)


class TurnLifecycle(TurnLifecyclePort):
    """轮次生命周期 —— **只写新表** ✓。"""

    def __init__(
        self,
        *,
        journal: SessionJournal,
        events: EventPublisher,
    ) -> None:
        # ⚠️ **不再持旧表仓库** ✓ —— 轮次的写入只有 journal 一条路 ✓。
        self._journal = journal
        self._events = events

    async def start_turn(self, *, request: TurnRequest) -> None:
        """开始这一轮 —— **新表建一行** + 发「轮次开始」事件 ✓。

        ⚠️ **旧表不再写** ✓（停旧写 S-15b）—— 轮次只有一个落点 ✓。
        """
        # 领域实体**只在内存里**用来发事件 ✓（不再落库 ✓）。
        turn = Turn.create(
            id=TurnId(request.turn_id),
            tenant_id=TenantId(request.tenant_id),
            workspace_id=WorkspaceId(request.workspace_id),
            session_id=SessionId(request.session_id),
            user_input=request.user_input if not request.resume else "继续",
        )
        await self._journal.start_turn(
            turn_id=request.turn_id,
            tenant_id=request.tenant_id,
            workspace_id=request.workspace_id,
            session_id=request.session_id,
            idempotency_key=request.idempotency_key,
            key_strength=request.key_strength,
            agent_version=request.agent.agent_version,
            model_version=request.model or request.agent.model or "default",
            # 这一轮用户说了什么 ✓（任务卡片要显示 ✓）。
            user_input=request.user_input if not request.resume else "继续",
            trace_id=request.trace_id,
            # 路由决策随轮次留痕（``session_turns.route_decision``）——
            # **产出者是 Router**，这里只是把它带进轮次行。
            route_decision=dict(request.route_decision) if request.route_decision else None,
            # ⚠️ **入站序号** ✓（Router 方案 §4.2 ✓）—— **有值就排队** ✓
            # （轮次行先落 ``queued`` ✓ —— 等 FIFO 位 ✓）。
            ingress_seq=request.ingress_seq,
        )
        await self._events.publish(
            turn.raise_started_event(),
            tenant_id=request.tenant_id,
            workspace_id=request.workspace_id,
            trace_id=request.trace_id,
        )

    async def append_event(
        self, *, turn_id: UUID, seq: int, event_type: str, payload: dict[str, Any]
    ) -> None:
        """把一个 chunk 落进事件流 ✓（**落库先于投递**）。"""
        await self._journal.append_event(
            turn_id=turn_id, seq=seq, event_type=event_type, payload=payload
        )

    async def next_event_seq(self, *, turn_id: UUID) -> int:
        """这一轮的下一个事件序号 ✓（**号统一从库里取** ✓）。"""
        return await self._journal.next_event_seq(turn_id=turn_id)

    async def finish_turn(
        self,
        *,
        turn_id: UUID,
        status: str,
        final_response: str = "",
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        cost_usd: float | None = None,
        error_code: str | None = None,
        error_message: str = "",
    ) -> None:
        """轮次落到终态 —— **只落新表** ✓（停旧写 S-15b ✓）。

        ⚠️ **token 数与最终回复不再入库** ✓ —— 新表没有这两列 ✓；回复在
        **事件流**里 ✓（``done`` 事件 ✓），token 数在 ``usage`` 事件里 ✓。
        """
        await self._journal.finish_turn(
            turn_id=turn_id,
            status=status,
            error_code=error_code,
            cost_usd=cost_usd,
        )

    async def fail_turn(self, *, turn_id: UUID, code: str, message: str = "") -> None:
        """失败落库 —— **尽力而为，不抛**（失败也得留下痕迹 ✓）。"""
        try:
            await self.finish_turn(
                turn_id=turn_id,
                status=TurnStatus.CANCELLED.value
                if code == "TURN_CANCELLED"
                else TurnStatus.FAILED.value,
                error_code=code,
                error_message=message,
            )
        except Exception:
            _log.exception("failed to persist failed turn turn_id=%s", turn_id)

    async def mark_delivered(self, *, turn_id: UUID) -> None:
        """事件已投递 ✓。"""
        await self._journal.mark_delivered(turn_id=turn_id)

    async def mark_waiting_approval(self, *, turn_id: UUID, pending: Mapping[str, Any]) -> None:
        """审批挂起 → 轮次落库 + 状态转 ``waiting`` ✓（Session 方案 §8）。"""
        await self._journal.write_pending_approval(turn_id=turn_id, pending=dict(pending))


__all__ = ["TurnLifecycle"]
