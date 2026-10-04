"""Channel application-layer ports (Protocols).

Each Protocol is the contract that an adapter implements. The service
layer depends ONLY on these — concrete adapters (SQL, crypto, HTTP,
inbound/outbound adapters) live in ``adapter/``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from datetime import datetime
    from uuid import UUID

    from qzdap.modules.channel.domain.entities import Channel, ChannelDelivery
    from qzdap.modules.channel.domain.value_objects import ChannelType
    from qzdap_schema.ids import ChannelId, TenantId

# ── Persistence ───────────────────────────────────────────────────────────


@runtime_checkable
class ChannelRepository(Protocol):
    async def add(self, channel: Channel) -> None: ...
    async def get(self, *, tenant_id: TenantId, channel_id: ChannelId) -> Channel | None: ...
    async def get_by_id(self, channel_id: ChannelId) -> Channel | None: ...
    async def list(
        self,
        *,
        tenant_id: TenantId,
        workspace_id: UUID | None = None,
        enabled_only: bool = False,
        limit: int = 100,
    ) -> list[Channel]: ...
    async def update(self, channel: Channel) -> None: ...
    async def delete(self, *, tenant_id: TenantId, channel_id: ChannelId) -> bool: ...


@runtime_checkable
class ChannelDeliveryRepository(Protocol):
    async def add(self, delivery: ChannelDelivery) -> None: ...
    async def get(self, *, tenant_id: TenantId, delivery_id: UUID) -> ChannelDelivery | None: ...
    async def list_for_channel(
        self,
        *,
        tenant_id: TenantId,
        channel_id: ChannelId,
        limit: int = 50,
    ) -> list[ChannelDelivery]: ...
    async def update(self, delivery: ChannelDelivery) -> None: ...


@runtime_checkable
class WebhookSecretRepository(Protocol):
    async def add(
        self,
        *,
        tenant_id: TenantId,
        channel_type: ChannelType,
        label: str,
        encrypted_payload: bytes,
        key_version: int = 1,
    ) -> UUID: ...
    async def get(self, *, tenant_id: TenantId, secret_id: UUID) -> bytes | None: ...
    async def delete(self, *, tenant_id: TenantId, secret_id: UUID) -> bool: ...


# ── Crypto ────────────────────────────────────────────────────────────────


@runtime_checkable
class WebhookSecretCipher(Protocol):
    """Encrypts / decrypts webhook HMAC secrets."""

    def encrypt(self, plaintext: bytes) -> bytes: ...
    def decrypt(self, blob: bytes) -> bytes: ...


# ── Inbound / outbound ───────────────────────────────────────────────────


@dataclass(slots=True, frozen=True)
class ParsedMessage:
    """A normalized webhook payload after channel-specific parsing."""

    external_user_id: str
    external_chat_id: str
    external_message_id: str | None
    text: str
    metadata: dict[str, Any] = dict  # type: ignore[assignment]


@runtime_checkable
class InboundAdapter(Protocol):
    """Parses a raw webhook envelope into a normalized message."""

    channel_type: ChannelType

    def parse_webhook(
        self,
        *,
        body: bytes,
        headers: dict[str, str],
    ) -> ParsedMessage: ...


@runtime_checkable
class OutboundAdapter(Protocol):
    """Sends an outbound reply through the channel API."""

    channel_type: ChannelType

    async def send_reply(
        self,
        *,
        external_chat_id: str,
        text: str,
        metadata: dict[str, Any],
    ) -> str | None:  # returns external_message_id when supported
        ...


# ── Infrastructure (clock / ids) ──────────────────────────────────────────


@runtime_checkable
class ClockPort(Protocol):
    def now(self) -> datetime: ...


@runtime_checkable
class IdGeneratorPort(Protocol):
    def new_id(self) -> UUID: ...


# ── Event publisher ──────────────────────────────────────────────────────


@runtime_checkable
class ChannelEventPublisher(Protocol):
    async def publish(
        self,
        event: object,
        *,
        tenant_id: TenantId,
        workspace_id: UUID | None,
        trace_id: str | None = None,
    ) -> None: ...


__all__ = [
    "ChannelDeliveryRepository",
    "ChannelEventPublisher",
    "ChannelRepository",
    "ClockPort",
    "IdGeneratorPort",
    "InboundAdapter",
    "OutboundAdapter",
    "ParsedMessage",
    "WebhookSecretCipher",
    "WebhookSecretRepository",
]
