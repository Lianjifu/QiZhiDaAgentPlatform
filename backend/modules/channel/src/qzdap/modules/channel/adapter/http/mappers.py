"""HTTP DTO ↔ domain converters."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from qzdap.modules.channel.adapter.http.dto import (
    ChannelListResponse,
    ChannelResponse,
    DeliveryResponse,
)

if TYPE_CHECKING:
    from qzdap.modules.channel.domain.entities import Channel, ChannelDelivery


def channel_to_response(ch: Channel) -> ChannelResponse:
    return ChannelResponse(
        id=UUID(str(ch.id)),
        tenant_id=UUID(str(ch.tenant_id)),
        workspace_id=UUID(str(ch.workspace_id)) if ch.workspace_id else None,
        type=ch.type.value,
        name=ch.name,
        external_id=ch.external_id,
        status=ch.status.value,
        inbound_path=ch.inbound_path,
        has_webhook_secret=ch.webhook_secret_id is not None,
        created_at=ch.created_at.isoformat(),
        updated_at=ch.updated_at.isoformat(),
    )


def channel_list_to_response(items: list[Channel]) -> ChannelListResponse:
    return ChannelListResponse(items=[channel_to_response(c) for c in items])


def delivery_to_response(d: ChannelDelivery) -> DeliveryResponse:
    return DeliveryResponse(
        id=d.id,
        tenant_id=UUID(str(d.tenant_id)),
        channel_id=UUID(str(d.channel_id)),
        direction=d.direction,
        external_message_id=d.external_message_id,
        status=d.status.value,
        error_code=d.error_code,
        payload_summary=dict(d.payload_summary),
        created_at=d.created_at.isoformat(),
        delivered_at=d.delivered_at.isoformat() if d.delivered_at else None,
    )


__all__ = [
    "channel_list_to_response",
    "channel_to_response",
    "delivery_to_response",
]
