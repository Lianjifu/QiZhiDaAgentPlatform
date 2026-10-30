"""渠道入站 → 一轮会话 → 出站投递（**渠道侧的驱动**）。

⚠️ **它取代的是旧的 ``dispatch_subscriber.py``**（Gateway 方案 §10 Stage 4a，
台账 **G9**）—— 旧文件走的是「总线 → 订阅者 → 临时会话 → 第二套 turn 实现」
（``use_cases/run_turn_to_completion.py``，台账 **X2**）✗。现在：

- 会话**按渠道 + 聊天粘住**（台账 **R1** ✓）—— 同一个 chat 复用同一个会话；
- 跑一轮走**唯一 turn 实现**（Session 层的 ``CopilotSessionService`` → 契约层
  的 ``TurnRunner`` ✓）；
- 幂等只有**一个来源**：Gateway ③ 派生的键（``message.idempotency``）→
  会话层消费 ✓（web 侧也是同一条路 ✓）。

⚠️ **为什么不再自己 claim**：旧的订阅者调 ``gateway.claim``，而会话层内部
还会再 claim 一次 —— **两把键、两个作用域**（一个是渠道 id，一个是渠道类型）
✗。现在只有会话层那一把 ✓：同一平台消息重投 → 命中重复 → 不跑第二轮 ✓。

**失败不炸掉总线**：异常记日志后吞掉（总线会记 handler 异常；这里再记一份
领域级摘要 ✓）。
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from qzdap.modules.channel.adapter.outbound.channel_outbox_dispatcher import (
    ChannelOutboxDispatcher,
)
from qzdap_agent_runtime.gateway.identity import ServiceAccount
from qzdap_agent_runtime.gateway.outbound import ResultSink
from qzdap_agent_runtime.gateway.types import InboundMessage
from qzdap_agent_runtime.outbox import (
    IM_REPLY_EVENT_TYPE,
    DispatchError,
    OutboxEvent,
    OutboxRepository,
)
from qzdap_agent_runtime.router.session_key import derive_session_key
from qzdap_agent_runtime.session.channel_turn import (
    ChannelTurnFactoryPort,
    ChannelTurnRequest,
)

if TYPE_CHECKING:
    from uuid import UUID

    from qzdap.modules.channel.application.ports import ChannelRepository

_log = logging.getLogger("qzdap.channel.dispatch")

DEFAULT_MODEL = "default"
DEFAULT_TIMEOUT_SECONDS = 60

#: 总线的订阅键 = 事件类名（``EventEnvelope.event_name``）。
INBOUND_MESSAGE_EVENT = InboundMessage.__name__


class ChannelTurnDispatcher:
    """把标准入站消息变成**一轮会话**，再把结果投递回渠道 ✓。"""

    def __init__(
        self,
        *,
        channel_repository: ChannelRepository,
        turn_factory: ChannelTurnFactoryPort,
        sink: ResultSink,
        open_session: Any,
        outbox: OutboxRepository | None = None,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self._channels = channel_repository
        self._turns = turn_factory
        self._sink = sink
        self._open_session = open_session
        # 出站队列 —— **回复先入队、再投递** ✓（投递失败 worker 能重试 ✓）。
        self._outbox = outbox
        # 投递**只有一份实现** ✓ —— 即时投递与 worker 重试都走它 ✓。
        self._dispatcher = ChannelOutboxDispatcher(sink=sink)
        self._timeout = timeout_seconds

    async def install(self, event_bus: Any) -> None:
        """Subscribe to the inbound message event.

        ⚠️ **键是事件类名**（总线按类名路由）—— 不是 dotted 的 topic 串。
        """
        await event_bus.subscribe(INBOUND_MESSAGE_EVENT, self._handle_envelope)
        _log.info(
            "channel turn dispatcher installed",
            extra={"event_name": INBOUND_MESSAGE_EVENT},
        )

    # ── handler ─────────────────────────────────────────────────────────

    async def _handle_envelope(self, envelope: Any) -> None:
        """Bus-level entrypoint; payload is dict from ``EventEnvelope``."""
        if isinstance(envelope, dict):
            payload = envelope.get("payload", envelope)
        else:
            payload = getattr(envelope, "payload", None) or {}
        if not isinstance(payload, dict):
            _log.warning("envelope payload is not a dict: %r", payload)
            return
        try:
            message = InboundMessage.from_payload(payload)
        except (KeyError, ValueError, TypeError):
            _log.exception("invalid inbound message payload: %r", payload)
            return
        await self._handle_message(message)

    async def _handle_message(self, message: InboundMessage) -> None:
        """Domain-level dispatch."""
        channel_id = message.channel_id
        tenant_id = message.actor.tenant_id

        if channel_id is None:
            _log.warning("inbound message has no channel id; dropping")
            return

        channel = await self._channels.get_by_id(channel_id)
        if channel is None:
            _log.warning(
                "channel not found; dropping event",
                extra={
                    "channel_id": str(channel_id),
                    "tenant_id": str(tenant_id),
                },
            )
            return

        # 物化 IM 的 actor —— 渠道登记的服务账号（不是全局常量）。
        account = ServiceAccount.from_mapping(getattr(channel, "service_account", None))
        if account is None:
            _log.error(
                "channel has no service account registered; dropping event",
                extra={
                    "channel_id": str(channel_id),
                    "tenant_id": str(tenant_id),
                },
            )
            return

        chat_id = message.external_chat_id
        channel_type = str(message.channel_type)
        request = ChannelTurnRequest(
            tenant_id=tenant_id,
            workspace_id=channel.workspace_id,
            owner_id=account.user_id,
            agent_id=account.agent_id,
            agent_version=account.agent_version,
            # **粘性的唯一依据** ✓ —— 同一个渠道 + 同一个聊天 = 同一个会话。
            # ⚠️ **哈希版** ✓（Router 方案 §4.1 ✓ —— 台账 R4 ✓）—— 旧的
            # 冒号拼接版已删 ✓ —— 这里的 key 会进数据库 ✓ → **不能带原文**
            # （渠道 ID / 群 ID 是身份 ✓ —— §12.2 的观测约束 ✓）。
            channel_session_key=derive_session_key(
                tenant_id=str(tenant_id),
                workspace_id=str(channel.workspace_id),
                channel_type=channel_type,
                channel_id=str(channel_id),
                external_chat_id=str(chat_id),
                external_user_id=str(account.user_id),
            ),
            channel_type=message.channel_type,
            user_input=f"[channel={channel_type} chat={chat_id}] {message.text}",
            idempotency=message.idempotency,
            metadata={
                "channel_id": str(channel_id),
                "channel_type": channel_type,
                "external_chat_id": chat_id,
                # ⚠️ **服务账号的角色** ✓（台账 R19 ✓）—— Router 的「用户标签」
                # 规则要它 ✓（渠道侧只负责带过来 ✓ —— 路由判断在 Router 侧 ✓）。
                "roles": list(account.roles),
            },
        )

        try:
            result = await asyncio.wait_for(self._run_turn(request), timeout=self._timeout)
        except Exception:
            _log.exception(
                "channel turn failed",
                extra={
                    "tenant_id": str(tenant_id),
                    "channel_id": str(channel_id),
                },
            )
            return

        if not result.final_message or result.turn_id is None:
            return

        await self._send_reply(
            message=message,
            channel_type=getattr(channel, "type", message.channel_type),
            text=result.final_message[:4096],
            turn_id=result.turn_id,
        )

    # ── helpers ──────────────────────────────────────────────────────────

    async def _run_turn(self, request: ChannelTurnRequest) -> Any:
        """跑一轮 —— **请求级 DB 会话**包住整轮 ✓。"""
        async with self._open_session() as db_session:
            service = self._turns.for_session(db_session)
            return await service.run(request)

    async def _send_reply(
        self,
        *,
        message: InboundMessage,
        channel_type: Any,
        text: str,
        turn_id: UUID | None,
    ) -> None:
        """出站 —— **先入队、再投递** ✓（事务性 outbox ✓）。

        ⚠️ **入队先于投递** ✓ —— 投递失败时那一行还在队列里 → worker 会重试
        ✓（投递成功才标 delivered ✓）。没有这一步，一次网络抖动就**丢消息** ✗✗。
        """
        if turn_id is None:
            return
        payload = {
            "content": text,
            "channel_type": str(channel_type),
            "chat_id": message.external_chat_id,
            "trace_id": message.trace_id or "",
        }
        if self._outbox is None:
            # 没有队列（未接线）→ **直投**（不丢消息 ✓，但没有重试 ✗）。
            try:
                await self._deliver_now(
                    OutboxEvent(
                        turn_id=str(turn_id),
                        seq=0,
                        event_type=IM_REPLY_EVENT_TYPE,
                        payload=payload,
                        delivery_status="pending",
                        delivery_attempts=0,
                    )
                )
            except DispatchError as exc:
                # 投递失败**不炸主链路** ✓（那一轮已经成功 ✓）。
                _log.warning(
                    "im reply not delivered: %s",
                    exc,
                    extra={"channel_id": str(message.channel_id)},
                )
            return

        outbound = await self._outbox.enqueue(
            turn_id=str(turn_id),
            event_type=IM_REPLY_EVENT_TYPE,
            payload=payload,
        )
        event = OutboxEvent(
            turn_id=outbound.turn_id,
            seq=outbound.seq,
            event_type=outbound.event_type,
            payload=payload,
            delivery_status="pending",
            delivery_attempts=0,
        )
        try:
            await self._deliver_now(event)
        except DispatchError as exc:
            # 投递失败 → **留在队列里** ✓，worker 稍后重试 ✓。
            await self._outbox.mark_failed(outbound.turn_id, outbound.seq, 1, str(exc))
            _log.warning(
                "im reply queued for retry: turn_id=%s error=%s",
                outbound.turn_id,
                exc,
                extra={"channel_id": str(message.channel_id)},
            )
            return
        await self._outbox.mark_delivered(outbound.turn_id, outbound.seq)

    async def _deliver_now(self, event: OutboxEvent) -> None:
        """即时投递 —— 走**统一编码 + 投递**（Gateway ① 的出站，§6）✓。"""
        await self._dispatcher.dispatch(event)


__all__ = ["INBOUND_MESSAGE_EVENT", "ChannelTurnDispatcher"]
