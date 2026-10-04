"""ChannelService — application-layer orchestrator for the channel module.

Responsibilities:

- register / list / disable / rotate secrets for channels
- verify inbound webhook signatures (HMAC-SHA256 + timestamp skew)
- dispatch inbound messages to ``InboundAdapter`` for parsing
- persist ``ChannelDelivery`` rows (inbound + outbound)
- push domain events via ``ChannelEventPublisher``

P6 scope: domain logic only. Real outbound HTTP and HTTP route are
wired in step 7 (adapters).
"""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from qzdap.modules.channel.domain.entities import (
    Channel,
    ChannelDelivery,
    make_channel,
    make_inbound_delivery,
    make_outbound_delivery,
)
from qzdap.modules.channel.domain.errors import (
    ChannelDeliveryFailed,
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

if TYPE_CHECKING:
    from uuid import UUID

    from qzdap.modules.channel.application.ports import (
        ChannelDeliveryRepository,
        ChannelEventPublisher,
        ChannelRepository,
        ClockPort,
        IdGeneratorPort,
        InboundAdapter,
        OutboundAdapter,
        WebhookSecretCipher,
        WebhookSecretRepository,
    )
    from qzdap_schema.ids import ChannelId, TenantId

DEFAULT_TIMESTAMP_TOLERANCE_SECONDS = 300


@dataclass(slots=True, frozen=True)
class ChannelService:
    channel_repo: ChannelRepository
    delivery_repo: ChannelDeliveryRepository
    secret_repo: WebhookSecretRepository
    cipher: WebhookSecretCipher
    clock: ClockPort
    ids: IdGeneratorPort
    publisher: ChannelEventPublisher | None = None
    default_timestamp_tolerance_seconds: int = DEFAULT_TIMESTAMP_TOLERANCE_SECONDS

    # ── Registration / admin ────────────────────────────────────────────────

    async def register_channel(
        self,
        *,
        tenant_id: TenantId,
        workspace_id: UUID | None,
        type: ChannelType,
        name: str,
        external_id: str,
        inbound_path: str,
        webhook_secret: str | None = None,
        outbound_config: dict[str, Any] | None = None,
    ) -> Channel:
        secret_id: UUID | None = None
        if webhook_secret:
            blob = self.cipher.encrypt(webhook_secret.encode("utf-8"))
            secret_id = await self.secret_repo.add(
                tenant_id=tenant_id,
                channel_type=type,
                label=f"{name}.webhook",
                encrypted_payload=blob,
            )
        channel = make_channel(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            type=type,
            name=name,
            external_id=external_id,
            inbound_path=inbound_path,
            webhook_secret_id=secret_id,
            outbound_config=outbound_config,
        )
        await self.channel_repo.add(channel)
        return channel

    async def list_channels(
        self,
        *,
        tenant_id: TenantId,
        workspace_id: UUID | None = None,
        enabled_only: bool = False,
        limit: int = 100,
    ) -> list[Channel]:
        return await self.channel_repo.list(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            enabled_only=enabled_only,
            limit=limit,
        )

    async def set_status(
        self,
        *,
        tenant_id: TenantId,
        channel_id: ChannelId,
        status: ChannelStatus,
    ) -> Channel:
        channel = await self.channel_repo.get(tenant_id=tenant_id, channel_id=channel_id)
        if channel is None:
            raise ChannelNotFound(
                f"channel {channel_id} not found",
                code="CHANNEL_NOT_FOUND",
            )
        updated = channel.with_status(status)
        await self.channel_repo.update(updated)
        return updated

    # ── Webhook handling ────────────────────────────────────────────────────

    async def handle_webhook(
        self,
        *,
        tenant_id: TenantId,
        channel_id: ChannelId,
        body: bytes,
        headers: dict[str, str],
        inbound_registry: dict[ChannelType, InboundAdapter],
        tolerance_seconds: int | None = None,
    ) -> ChannelDelivery:
        """Verify signature, parse envelope, persist delivery.

        Returns the persisted ``ChannelDelivery`` (status=PENDING).
        The caller is responsible for dispatching the message into
        ``agent_runtime.start_turn``; this service exposes the parsed
        message via the delivery's payload summary.
        """
        tolerance = tolerance_seconds or self.default_timestamp_tolerance_seconds

        channel = await self.channel_repo.get(tenant_id=tenant_id, channel_id=channel_id)
        if channel is None:
            raise ChannelNotFound(
                f"channel {channel_id} not found",
                code="CHANNEL_NOT_FOUND",
            )

        if channel.status is not ChannelStatus.ACTIVE:
            await self._reject(
                tenant_id=tenant_id,
                channel_id=channel_id,
                reason_code="CHANNEL_DISABLED",
            )
            raise ChannelDisabled(
                f"channel {channel_id} is {channel.status.value}",
                code="CHANNEL_DISABLED",
            )

        # Decrypt the HMAC secret (only if a secret is configured; the
        # web channel can opt out of signing by passing an empty secret).
        secret_bytes = b""
        if channel.webhook_secret_id is not None:
            blob = await self.secret_repo.get(
                tenant_id=tenant_id, secret_id=channel.webhook_secret_id
            )
            if blob is not None:
                secret_bytes = self.cipher.decrypt(blob)

        # Validate timestamp skew + HMAC signature (publish rejects).
        try:
            await self._verify_signature(
                secret=secret_bytes,
                body=body,
                headers=headers,
                tolerance_seconds=tolerance,
            )
        except (WebhookSignatureInvalid, WebhookTimestampSkew) as exc:
            code = (
                "WEBHOOK_TIMESTAMP_SKEW"
                if isinstance(exc, WebhookTimestampSkew)
                else "WEBHOOK_SIGNATURE_INVALID"
            )
            await self._reject(
                tenant_id=tenant_id,
                channel_id=channel_id,
                reason_code=code,
            )
            raise

        # Pick the adapter and parse the envelope.
        adapter = inbound_registry.get(channel.type)
        if adapter is None:
            raise ChannelError(
                f"no inbound adapter registered for channel type {channel.type.value}",
                code="INBOUND_ADAPTER_MISSING",
            )

        parsed = adapter.parse_webhook(body=body, headers=headers)
        delivery = make_inbound_delivery(
            tenant_id=tenant_id,
            channel_id=channel_id,
            external_message_id=parsed.external_message_id,
            payload_summary={
                "external_user_id": parsed.external_user_id,
                "external_chat_id": parsed.external_chat_id,
                "text": parsed.text[:4096],
                "metadata": dict(parsed.metadata) if parsed.metadata else {},
            },
        )
        await self.delivery_repo.add(delivery)

        if self.publisher is not None:
            await self.publisher.publish(
                ChannelMessageReceived(
                    channel_id=channel_id,
                    channel_type=channel.type.value,
                    external_user_id=parsed.external_user_id,
                    external_chat_id=parsed.external_chat_id,
                    text_preview=parsed.text[:200],
                    tenant_id=tenant_id,
                ),
                tenant_id=tenant_id,
                workspace_id=channel.workspace_id,
            )
        return delivery

    async def send_reply(
        self,
        *,
        tenant_id: TenantId,
        channel_id: ChannelId,
        external_chat_id: str,
        text: str,
        outbound_registry: dict[ChannelType, OutboundAdapter],
        metadata: dict[str, Any] | None = None,
    ) -> ChannelDelivery:
        channel = await self.channel_repo.get(tenant_id=tenant_id, channel_id=channel_id)
        if channel is None:
            raise ChannelNotFound(
                f"channel {channel_id} not found",
                code="CHANNEL_NOT_FOUND",
            )
        if channel.status is not ChannelStatus.ACTIVE:
            raise ChannelDisabled(
                f"channel {channel_id} is {channel.status.value}",
                code="CHANNEL_DISABLED",
            )
        adapter = outbound_registry.get(channel.type)
        if adapter is None:
            raise ChannelError(
                f"no outbound adapter registered for channel type {channel.type.value}",
                code="OUTBOUND_ADAPTER_MISSING",
            )
        delivery = make_outbound_delivery(
            tenant_id=tenant_id,
            channel_id=channel_id,
            external_message_id=None,
            payload_summary={
                "external_chat_id": external_chat_id,
                "text": text[:4096],
                "metadata": dict(metadata or {}),
            },
        )
        await self.delivery_repo.add(delivery)
        try:
            external_msg_id = await adapter.send_reply(
                external_chat_id=external_chat_id,
                text=text,
                metadata=dict(metadata or {}),
            )
            updated = delivery.with_status(
                DeliveryStatus.SENT,
                external_message_id=external_msg_id,
            )
            await self.delivery_repo.update(updated)
            if self.publisher is not None:
                await self.publisher.publish(
                    ChannelReplySent(
                        channel_id=channel_id,
                        delivery_id=delivery.id,
                        external_chat_id=external_chat_id,
                        tenant_id=tenant_id,
                    ),
                    tenant_id=tenant_id,
                    workspace_id=channel.workspace_id,
                )
        except ChannelDeliveryFailed:
            # Persist the failure then re-raise the original error so
            # callers still see ChannelDeliveryFailed, not bare Exception.
            failed = delivery.with_status(
                DeliveryStatus.FAILED,
                error_code="CHANNEL_DELIVERY_FAILED",
            )
            await self.delivery_repo.update(failed)
            raise
        except Exception as exc:
            failed = delivery.with_status(DeliveryStatus.FAILED, error_code=type(exc).__name__)
            await self.delivery_repo.update(failed)
            raise ChannelDeliveryFailed(
                f"outbound send failed: {exc}",
                code="CHANNEL_DELIVERY_FAILED",
            ) from exc
        else:
            return updated

    # ── Signature verification ─────────────────────────────────────────────

    async def _verify_signature(
        self,
        *,
        secret: bytes,
        body: bytes,
        headers: dict[str, str],
        tolerance_seconds: int,
    ) -> None:
        ts_raw = headers.get("x-webhook-timestamp") or headers.get("X-Webhook-Timestamp")
        sig_raw = headers.get("x-webhook-signature") or headers.get("X-Webhook-Signature")
        if not ts_raw or not sig_raw:
            raise WebhookSignatureInvalid(
                "missing X-Webhook-Timestamp / X-Webhook-Signature",
                code="WEBHOOK_SIGNATURE_INVALID",
            )
        try:
            ts = int(ts_raw)
        except ValueError as exc:
            raise WebhookSignatureInvalid(
                "X-Webhook-Timestamp must be an integer",
                code="WEBHOOK_SIGNATURE_INVALID",
            ) from exc

        now = int(self.clock.now().timestamp())
        if abs(now - ts) > tolerance_seconds:
            raise WebhookTimestampSkew(
                f"webhook timestamp {ts} outside ±{tolerance_seconds}s",
                code="WEBHOOK_TIMESTAMP_SKEW",
            )

        if secret:
            expected = hmac.new(
                secret,
                f"{ts}.".encode() + body,
                hashlib.sha256,
            ).hexdigest()
            provided = sig_raw.split("=", 1)[-1] if "=" in sig_raw else sig_raw
            if not hmac.compare_digest(expected, provided):
                raise WebhookSignatureInvalid(
                    "webhook signature does not match",
                    code="WEBHOOK_SIGNATURE_INVALID",
                )

    async def _reject(
        self,
        *,
        tenant_id: TenantId,
        channel_id: ChannelId,
        reason_code: str,
    ) -> None:
        if self.publisher is None:
            return
        await self.publisher.publish(
            ChannelWebhookRejected(
                channel_id=channel_id,
                reason_code=reason_code,
                tenant_id=tenant_id,
            ),
            tenant_id=tenant_id,
            workspace_id=None,
        )


__all__ = ["DEFAULT_TIMESTAMP_TOLERANCE_SECONDS", "ChannelService"]
