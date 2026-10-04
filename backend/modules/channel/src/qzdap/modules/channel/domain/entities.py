"""Channel domain entities — frozen dataclasses (slots=True).

Both entities are immutable. State transitions (``status`` field
updates) return a new instance via ``with_*`` methods, mirroring the
model module's pattern.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from qzdap.modules.channel.domain.value_objects import (
    ChannelStatus,
    ChannelType,
    DeliveryStatus,
)
from qzdap_schema.ids import ChannelId, TenantId


@dataclass(slots=True, frozen=True)
class Channel:
    """A configured inbound channel (Feishu, DingTalk, WeChatWork, Web).

    ``webhook_secret_id`` points at an encrypted blob stored in
    ``channel_secrets`` (AES-GCM, same envelope as ``ModelCredential``).
    The raw HMAC secret never lives on this row.
    """

    id: ChannelId
    tenant_id: TenantId
    workspace_id: UUID | None
    type: ChannelType
    name: str
    external_id: str
    webhook_secret_id: UUID | None
    status: ChannelStatus
    inbound_path: str
    outbound_config: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def with_status(self, status: ChannelStatus) -> Channel:
        from datetime import datetime as _dt

        return Channel(
            id=self.id,
            tenant_id=self.tenant_id,
            workspace_id=self.workspace_id,
            type=self.type,
            name=self.name,
            external_id=self.external_id,
            webhook_secret_id=self.webhook_secret_id,
            status=status,
            inbound_path=self.inbound_path,
            outbound_config=dict(self.outbound_config),
            created_at=self.created_at,
            updated_at=_dt.now(UTC),
        )

    def with_outbound_config(self, cfg: dict[str, Any]) -> Channel:
        from datetime import datetime as _dt

        return Channel(
            id=self.id,
            tenant_id=self.tenant_id,
            workspace_id=self.workspace_id,
            type=self.type,
            name=self.name,
            external_id=self.external_id,
            webhook_secret_id=self.webhook_secret_id,
            status=self.status,
            inbound_path=self.inbound_path,
            outbound_config=dict(cfg),
            created_at=self.created_at,
            updated_at=_dt.now(UTC),
        )

    def with_secret(self, secret_id: UUID | None) -> Channel:
        from datetime import datetime as _dt

        return Channel(
            id=self.id,
            tenant_id=self.tenant_id,
            workspace_id=self.workspace_id,
            type=self.type,
            name=self.name,
            external_id=self.external_id,
            webhook_secret_id=secret_id,
            status=self.status,
            inbound_path=self.inbound_path,
            outbound_config=dict(self.outbound_config),
            created_at=self.created_at,
            updated_at=_dt.now(UTC),
        )


def make_channel(
    *,
    tenant_id: TenantId,
    type: ChannelType,
    name: str,
    external_id: str,
    inbound_path: str,
    workspace_id: UUID | None = None,
    webhook_secret_id: UUID | None = None,
    outbound_config: dict[str, Any] | None = None,
) -> Channel:
    """Factory with input validation."""
    if not name or not name.strip():
        raise ValueError("channel name must be non-empty")
    if len(name) > 256:
        raise ValueError("channel name too long (max 256 chars)")
    if not external_id or not external_id.strip():
        raise ValueError("external_id must be non-empty")
    if not inbound_path.startswith("/"):
        raise ValueError("inbound_path must start with a '/'")
    if len(inbound_path) > 512:
        raise ValueError("inbound_path too long (max 512 chars)")
    return Channel(
        id=ChannelId(uuid4()),
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        type=type,
        name=name,
        external_id=external_id,
        webhook_secret_id=webhook_secret_id,
        status=ChannelStatus.ACTIVE,
        inbound_path=inbound_path,
        outbound_config=dict(outbound_config or {}),
    )


@dataclass(slots=True, frozen=True)
class ChannelDelivery:
    """An inbound or outbound message processed by the channel."""

    id: UUID
    tenant_id: TenantId
    channel_id: ChannelId
    direction: str  # "inbound" | "outbound"
    external_message_id: str | None
    session_id: UUID | None
    payload_summary: dict[str, Any]
    status: DeliveryStatus
    error_code: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    delivered_at: datetime | None = None

    def with_status(
        self,
        status: DeliveryStatus,
        *,
        error_code: str | None = None,
        external_message_id: str | None = None,
    ) -> ChannelDelivery:
        from datetime import datetime as _dt

        delivered = self.delivered_at
        if status in (DeliveryStatus.SENT, DeliveryStatus.DELIVERED):
            delivered = delivered or _dt.now(UTC)
        return ChannelDelivery(
            id=self.id,
            tenant_id=self.tenant_id,
            channel_id=self.channel_id,
            direction=self.direction,
            external_message_id=(
                external_message_id if external_message_id is not None else self.external_message_id
            ),
            session_id=self.session_id,
            payload_summary=dict(self.payload_summary),
            status=status,
            error_code=error_code,
            created_at=self.created_at,
            delivered_at=delivered,
        )


def make_inbound_delivery(
    *,
    tenant_id: TenantId,
    channel_id: ChannelId,
    external_message_id: str | None,
    payload_summary: dict[str, Any],
    session_id: UUID | None = None,
) -> ChannelDelivery:
    if payload_summary is None:
        raise ValueError("payload_summary must not be None")
    return ChannelDelivery(
        id=uuid4(),
        tenant_id=tenant_id,
        channel_id=channel_id,
        direction="inbound",
        external_message_id=external_message_id,
        session_id=session_id,
        payload_summary=dict(payload_summary),
        status=DeliveryStatus.PENDING,
    )


def make_outbound_delivery(
    *,
    tenant_id: TenantId,
    channel_id: ChannelId,
    external_message_id: str | None,
    payload_summary: dict[str, Any],
) -> ChannelDelivery:
    if payload_summary is None:
        raise ValueError("payload_summary must not be None")
    return ChannelDelivery(
        id=uuid4(),
        tenant_id=tenant_id,
        channel_id=channel_id,
        direction="outbound",
        external_message_id=external_message_id,
        session_id=None,
        payload_summary=dict(payload_summary),
        status=DeliveryStatus.PENDING,
    )


__all__ = [
    "Channel",
    "ChannelDelivery",
    "make_channel",
    "make_inbound_delivery",
    "make_outbound_delivery",
]
