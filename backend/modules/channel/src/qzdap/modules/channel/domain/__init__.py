"""Domain layer — Channel entities + value objects + errors + events.

All channel state lives here. Adapters (inbound/outbound HTTP, SQL
repositories, crypto wrappers) only translate between this domain and
external representations.
"""

from __future__ import annotations

from qzdap.modules.channel.domain.entities import Channel, ChannelDelivery
from qzdap.modules.channel.domain.errors import (
    ChannelDisabled,
    ChannelError,
    ChannelNotFound,
    WebhookSignatureInvalid,
    WebhookTimestampSkew,
)
from qzdap.modules.channel.domain.events import (
    ChannelReplySent,
    ChannelWebhookRejected,
)
from qzdap.modules.channel.domain.value_objects import ChannelStatus, DeliveryStatus
from qzdap_agent_runtime.gateway.types import ChannelType
from qzdap_kernel.ids import ChannelId

__all__ = [
    "Channel",
    "ChannelDelivery",
    "ChannelDisabled",
    "ChannelError",
    "ChannelId",
    "ChannelNotFound",
    "ChannelReplySent",
    "ChannelStatus",
    "ChannelType",
    "ChannelWebhookRejected",
    "DeliveryStatus",
    "WebhookSignatureInvalid",
    "WebhookTimestampSkew",
]
