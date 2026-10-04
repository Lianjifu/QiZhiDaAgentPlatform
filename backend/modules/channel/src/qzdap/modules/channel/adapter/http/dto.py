"""HTTP DTOs for the channel module."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from uuid import UUID


class RegisterChannelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str = Field(pattern="^(feishu|dingtalk|wechatwork|web)$")
    name: str = Field(min_length=1, max_length=256)
    external_id: str = Field(min_length=1, max_length=256)
    inbound_path: str = Field(pattern="^/", max_length=512)
    workspace_id: UUID | None = None
    webhook_secret: str | None = Field(default=None, min_length=1)
    outbound_config: dict[str, Any] = Field(default_factory=dict)


class UpdateChannelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str | None = Field(default=None, pattern="^(active|disabled)$")
    outbound_config: dict[str, Any] | None = None
    webhook_secret: str | None = Field(default=None, min_length=1)


class ChannelResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    tenant_id: UUID
    workspace_id: UUID | None
    type: str
    name: str
    external_id: str
    status: str
    inbound_path: str
    has_webhook_secret: bool
    created_at: str
    updated_at: str


class ChannelListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ChannelResponse]


class DeliveryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    tenant_id: UUID
    channel_id: UUID
    direction: str
    external_message_id: str | None
    status: str
    error_code: str | None
    payload_summary: dict[str, Any]
    created_at: str
    delivered_at: str | None


class SendReplyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    external_chat_id: str = Field(min_length=1)
    text: str = Field(min_length=1, max_length=4096)
    metadata: dict[str, Any] = Field(default_factory=dict)


__all__ = [
    "ChannelListResponse",
    "ChannelResponse",
    "DeliveryResponse",
    "RegisterChannelRequest",
    "SendReplyRequest",
    "UpdateChannelRequest",
]
