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
    ChannelMessageReceived,
    ChannelReplySent,
    ChannelWebhookRejected,
)
from qzdap.modules.channel.domain.value_objects import (
    ChannelStatus,
    ChannelType,
    DeliveryStatus,
)
from qzdap_schema.ids import ChannelId

__all__ = [
    "Channel",
    "ChannelDelivery",
    "ChannelDisabled",
    "ChannelError",
    "ChannelId",
    "ChannelMessageReceived",
    "ChannelNotFound",
    "ChannelReplySent",
    "ChannelStatus",
    "ChannelType",
    "ChannelWebhookRejected",
    "DeliveryStatus",
    "WebhookSignatureInvalid",
    "WebhookTimestampSkew",
]
