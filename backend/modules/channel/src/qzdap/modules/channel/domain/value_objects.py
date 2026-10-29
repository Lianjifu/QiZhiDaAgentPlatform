"""Channel value objects — enums used across the module."""

from __future__ import annotations

from enum import StrEnum


class ChannelStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"


class DeliveryStatus(StrEnum):
    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"


__all__ = ["ChannelStatus", "DeliveryStatus"]
