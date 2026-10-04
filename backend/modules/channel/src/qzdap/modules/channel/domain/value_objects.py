"""Channel value objects — enums used across the module."""

from __future__ import annotations

from enum import StrEnum


class ChannelType(StrEnum):
    FEISHU = "feishu"
    DINGTALK = "dingtalk"
    WECHATWORK = "wechatwork"
    WEB = "web"


class ChannelStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"


class DeliveryStatus(StrEnum):
    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"


__all__ = ["ChannelStatus", "ChannelType", "DeliveryStatus"]
