"""Channel domain events — emitted through the messaging bus.

Topic conventions follow the governance audit recorder's
``build_default_topics()`` registration; channel.* events are appended
in step 7 when the audit subscriber wires them in.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from qzdap_kernel.events import DomainEvent

if TYPE_CHECKING:
    from uuid import UUID


# ⚠️ `ChannelMessageReceived` **已删除** —— 入站消息的形状由 Gateway 的
# `InboundMessage` 统一承担（§10 Stage 3 / 台账 G5）。它缺 `external_message_id`
# / `trace_id` / `payload_hash`，而且**从未被总线正确路由过**（按 dotted 的
# TOPIC 订阅，而总线按类名路由）—— 旧实现是一条**从未被触发**的链路。


@dataclass(slots=True, frozen=True)
class ChannelReplySent(DomainEvent):
    """An outbound reply was successfully delivered to the channel."""

    TOPIC = "channel.reply.sent"

    channel_id: UUID
    delivery_id: UUID
    external_chat_id: str
    tenant_id: UUID

    def _as_payload_dict(self) -> dict[str, Any]:
        # ⚠️ 方法名必须是 ``_as_payload_dict`` —— ``EventEnvelope.wrap`` 只认它。
        # 旧的 ``to_payload`` **从未被调用**，slots dataclass 的事件因此退化成了
        # ``{"value": "<repr>"}``，审计侧拿到的是字符串而不是字段。
        return {
            "channel_id": str(self.channel_id),
            "delivery_id": str(self.delivery_id),
            "external_chat_id": self.external_chat_id,
            "tenant_id": str(self.tenant_id),
        }


@dataclass(slots=True, frozen=True)
class ChannelWebhookRejected(DomainEvent):
    """A webhook was rejected (bad signature, skew, or disabled channel).

    ⚠️ **必须带 trace_id** —— 鉴权失败的请求往往在进入业务处理之前就结束了，
    没有 trace_id 就追不到（Gateway 方案 §2.3 的顺序规则 ② / §10 Stage 2 验收）。
    """

    TOPIC = "channel.webhook.rejected"

    channel_id: UUID
    reason_code: str
    tenant_id: UUID | None = None
    trace_id: str = ""

    def _as_payload_dict(self) -> dict[str, Any]:
        return {
            "channel_id": str(self.channel_id),
            "reason_code": self.reason_code,
            "tenant_id": str(self.tenant_id) if self.tenant_id else None,
            "trace_id": self.trace_id,
        }


# Topic groups used by the audit recorder when subscribing.
# ⚠️ 入站消息不在这里 —— 它的形状是 Gateway 的 `InboundMessage`（类名路由）。
CHANNEL_TOPICS: tuple[str, ...] = (
    ChannelReplySent.TOPIC,
    ChannelWebhookRejected.TOPIC,
)


__all__ = [
    "CHANNEL_TOPICS",
    "ChannelReplySent",
    "ChannelWebhookRejected",
]
