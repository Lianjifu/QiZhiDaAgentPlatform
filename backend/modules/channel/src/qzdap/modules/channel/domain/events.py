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


@dataclass(slots=True, frozen=True)
class ChannelMessageReceived(DomainEvent):
    """An inbound webhook was successfully verified and accepted."""

    TOPIC = "channel.message.received"

    channel_id: UUID
    channel_type: str
    external_user_id: str
    external_chat_id: str
    text_preview: str
    tenant_id: UUID

    def to_payload(self) -> dict[str, Any]:
        return {
            "channel_id": str(self.channel_id),
            "channel_type": self.channel_type,
            "external_user_id": self.external_user_id,
            "external_chat_id": self.external_chat_id,
            "text_preview": self.text_preview,
            "tenant_id": str(self.tenant_id),
        }


@dataclass(slots=True, frozen=True)
class ChannelReplySent(DomainEvent):
    """An outbound reply was successfully delivered to the channel."""

    TOPIC = "channel.reply.sent"

    channel_id: UUID
    delivery_id: UUID
    external_chat_id: str
    tenant_id: UUID

    def to_payload(self) -> dict[str, Any]:
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

    def to_payload(self) -> dict[str, Any]:
        return {
            "channel_id": str(self.channel_id),
            "reason_code": self.reason_code,
            "tenant_id": str(self.tenant_id) if self.tenant_id else None,
            "trace_id": self.trace_id,
        }


# Topic groups used by the audit recorder when subscribing.
CHANNEL_TOPICS: tuple[str, ...] = (
    ChannelMessageReceived.TOPIC,
    ChannelReplySent.TOPIC,
    ChannelWebhookRejected.TOPIC,
)


__all__ = [
    "CHANNEL_TOPICS",
    "ChannelMessageReceived",
    "ChannelReplySent",
    "ChannelWebhookRejected",
]
