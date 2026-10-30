"""**出站队列 → 渠道**的投递器（重试与死信的那一环 ✓）。

⚠️ **只有一份投递实现** ✓ —— IM 的**即时投递**（快路径）与 worker 的
**重试投递**都走这里 ✓（否则两处各写一遍投递逻辑 ✗✗）。

投递失败 → 抛 :class:`DispatchError` ✓（worker 据此记 FAILED / 进死信 ✓）；
「投递失败**不炸主链路**」✓ —— 出站失败不该让那一轮变成失败 ✓。
"""

from __future__ import annotations

import logging

from qzdap_agent_runtime.gateway.channels import capabilities_for
from qzdap_agent_runtime.gateway.outbound import OutboundTarget, ResultSink
from qzdap_agent_runtime.gateway.types import ChannelType
from qzdap_agent_runtime.outbox import DispatchError, OutboxEvent, to_result_event

_log = logging.getLogger("qzdap.channel.outbox")


class ChannelOutboxDispatcher:
    """把队列里的出站消息投给渠道 ✓。"""

    def __init__(self, *, sink: ResultSink) -> None:
        self._sink = sink

    async def dispatch(self, event: OutboxEvent) -> None:
        """投递一条出站消息 —— 失败**抛 DispatchError** ✓（worker 记账 ✓）。"""
        payload = dict(event.payload or {})
        text = str(payload.get("content") or payload.get("text") or "")
        if not text:
            raise DispatchError(f"outbox message {event.turn_id}/{event.seq} is empty")
        channel_type = str(payload.get("channel_type") or "")
        chat_id = str(payload.get("chat_id") or "")
        if not channel_type or not chat_id:
            raise DispatchError(
                f"outbox message {event.turn_id}/{event.seq} has no delivery target"
            )
        try:
            channel = ChannelType(channel_type)
        except ValueError as exc:
            raise DispatchError(f"unknown channel type {channel_type!r}") from exc

        outcome = await self._sink.deliver(
            to_result_event(event),
            target=OutboundTarget(
                channel_type=channel,
                external_chat_id=chat_id,
                capabilities=capabilities_for(channel),
                metadata={"turn_id": event.turn_id},
            ),
        )
        if not outcome.ok:
            _log.warning(
                "outbox delivery failed: turn_id=%s seq=%s status=%s error=%s",
                event.turn_id,
                event.seq,
                outcome.status,
                outcome.error,
            )
            raise DispatchError(f"{outcome.status}: {outcome.error}")


__all__ = ["ChannelOutboxDispatcher"]
