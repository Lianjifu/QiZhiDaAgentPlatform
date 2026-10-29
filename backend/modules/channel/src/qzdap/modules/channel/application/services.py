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
from qzdap_agent_runtime.gateway.identity import (
    REASON_TIMESTAMP_SKEW,
    HmacWebhookVerifier,
    Identity,
    IdentityRejected,
    IdentityRequest,
    IdentityVerifier,
    ServiceAccount,
)
from qzdap_kernel.contextvars import current_trace_id
from qzdap_observability.metrics import record_legacy_call

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
    # ② Auth Identity —— 验签实现住在 gateway/identity.py（§10 Stage 2）。
    # 留空则用默认的 HMAC 验签器（本层的 clock 决定时间戳容差）。
    identity: IdentityVerifier | None = None

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
        service_account: dict[str, Any] | None = None,
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
            service_account=service_account,
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
        trace_id: str = "",
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

        # ② Auth Identity：验签 + 时间戳容差。实现已迁到 gateway/identity.py，
        # 本层只负责把渠道配置（密钥 / 服务账号）喂给它，并把拒绝映射回本层的
        # 错误类型（对外契约不变：401 + WEBHOOK_*）。
        # ⚠️ 这里**不再打 G2 的点** —— 旧实现（渠道内的 `_verify_signature`）已经
        # 没了，现在跑的是新实现；继续打点会让「旧路径还在服役」永远为真。
        try:
            await self._verify_identity(
                tenant_id=tenant_id,
                channel=channel,
                body=body,
                headers=headers,
                secret=secret_bytes,
                tolerance_seconds=tolerance,
                trace_id=trace_id,
            )
        except IdentityRejected as exc:
            await self._reject(
                tenant_id=tenant_id,
                channel_id=channel_id,
                reason_code=exc.reason_code,
                trace_id=exc.trace_id,
            )
            if exc.reason_code == REASON_TIMESTAMP_SKEW:
                raise WebhookTimestampSkew(str(exc), code="WEBHOOK_TIMESTAMP_SKEW") from exc
            raise WebhookSignatureInvalid(str(exc), code="WEBHOOK_SIGNATURE_INVALID") from exc

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
            record_legacy_call("G5")  # ChannelMessageReceived 事件
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

    # ── ② Auth Identity ───────────────────────────────────────────────────

    async def _verify_identity(
        self,
        *,
        tenant_id: TenantId,
        channel: Channel,
        body: bytes,
        headers: dict[str, str],
        secret: bytes,
        tolerance_seconds: int,
        trace_id: str,
    ) -> Identity:
        """验签 + 归一身份 —— **实现住在 gateway/identity.py**（§10 Stage 2）。

        本层只提供「渠道配置 → 验签材料」：密钥来自渠道登记的密文，服务账号
        来自渠道登记的配置（IM 的 actor 由此物化，§3.2）。
        """
        verifier = self.identity or HmacWebhookVerifier(clock=self.clock)
        return await verifier.verify(
            IdentityRequest(
                trace_id=trace_id or current_trace_id() or "",
                headers=headers,
                body=body,
                secret=secret,
                tolerance_seconds=tolerance_seconds,
                tenant_id=tenant_id,
                workspace_id=channel.workspace_id,
                service_account=ServiceAccount.from_mapping(channel.service_account),
            )
        )

    async def _reject(
        self,
        *,
        tenant_id: TenantId,
        channel_id: ChannelId,
        reason_code: str,
        trace_id: str = "",
    ) -> None:
        if self.publisher is None:
            return
        await self.publisher.publish(
            ChannelWebhookRejected(
                channel_id=channel_id,
                reason_code=reason_code,
                tenant_id=tenant_id,
                trace_id=trace_id or current_trace_id() or "",
            ),
            tenant_id=tenant_id,
            workspace_id=None,
        )


__all__ = ["DEFAULT_TIMESTAMP_TOLERANCE_SECONDS", "ChannelService"]
