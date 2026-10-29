"""ChannelService — application-layer orchestrator for the channel module.

Responsibilities:

- register / list / disable / rotate secrets for channels
- verify inbound webhook signatures (HMAC-SHA256 + timestamp skew)
- dispatch inbound messages to ``MessageNormalizer`` for normalization
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
    ChannelServiceAccountMissing,
    WebhookSignatureInvalid,
    WebhookTimestampSkew,
)
from qzdap.modules.channel.domain.events import (
    ChannelReplySent,
    ChannelWebhookRejected,
)
from qzdap.modules.channel.domain.value_objects import ChannelStatus, DeliveryStatus
from qzdap_agent_runtime.gateway.channels import capabilities_for
from qzdap_agent_runtime.gateway.facade import (
    Gateway,
    GatewayChannelNotFound,
    GatewayNormalizerMissing,
)
from qzdap_agent_runtime.gateway.identity import (
    REASON_SERVICE_ACCOUNT_MISSING,
    REASON_TIMESTAMP_SKEW,
    IdentityRejected,
)
from qzdap_agent_runtime.gateway.types import RawIngress
from qzdap_kernel.contextvars import current_trace_id
from qzdap_schema.dtos.errors import ErrorCode

if TYPE_CHECKING:
    from uuid import UUID

    from qzdap.modules.channel.application.ports import (
        ChannelDeliveryRepository,
        ChannelEventPublisher,
        ChannelRepository,
        ClockPort,
        IdGeneratorPort,
        OutboundAdapter,
        WebhookSecretCipher,
        WebhookSecretRepository,
    )
    from qzdap_agent_runtime.gateway.types import ChannelType
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
    # Gateway 门面 —— ①→②→③ 的编排（查渠道 / 验签 / 归一化）。
    # ⚠️ Stage 4a 起，本层**不再自己串**这三段（§10 Stage 4a 的接管）。
    gateway: Gateway
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
                code=ErrorCode.CHANNEL_NOT_FOUND.value,
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
        tolerance_seconds: int | None = None,
        trace_id: str = "",
    ) -> ChannelDelivery:
        """受理一条 webhook —— **①→②→③ 交给 Gateway**，本层只做本层的职责。

        验签（②）、归一化（③）、幂等键的计算都在 :class:`Gateway` 里（§10
        Stage 4a 的接管）—— 渠道服务不再自己串这一段（**旧路径变小**）。
        本层保留的只有：渠道状态检查、**拒绝时写审计事件**、投递行落库、
        把标准入站消息发到总线。

        返回落库的 ``ChannelDelivery``（status=PENDING）。消息本体由事件带出去。
        """
        tolerance = tolerance_seconds or self.default_timestamp_tolerance_seconds

        channel = await self.channel_repo.get(tenant_id=tenant_id, channel_id=channel_id)
        if channel is None:
            raise ChannelNotFound(
                f"channel {channel_id} not found",
                code=ErrorCode.CHANNEL_NOT_FOUND.value,
            )

        if channel.status is not ChannelStatus.ACTIVE:
            await self._reject(
                tenant_id=tenant_id,
                channel_id=channel_id,
                reason_code=ErrorCode.CHANNEL_DISABLED.value,
            )
            raise ChannelDisabled(
                f"channel {channel_id} is {channel.status.value}",
                code=ErrorCode.CHANNEL_DISABLED.value,
            )

        raw = RawIngress(
            transport="webhook",
            channel_type=channel.type,
            channel_id=channel.id,
            capabilities=capabilities_for(channel.type),
            method="POST",
            path=f"/v1/channels/{channel_id}/webhook",
            headers=headers,
            body=body,
            query={},
            trace_id=trace_id or current_trace_id() or "",
        )
        try:
            accepted = await self.gateway.accept(
                raw,
                tolerance_seconds=tolerance,
            )
        except IdentityRejected as exc:
            # ② 拒绝 —— 写审计事件（**拒绝事件是当前职责，不是旧实现**），
            # 再映射回本层的错误类型（对外契约不变：401 + WEBHOOK_*）。
            await self._reject(
                tenant_id=tenant_id,
                channel_id=channel_id,
                reason_code=exc.reason_code,
                trace_id=exc.trace_id,
            )
            if exc.reason_code == REASON_TIMESTAMP_SKEW:
                raise WebhookTimestampSkew(
                    str(exc), code=ErrorCode.WEBHOOK_TIMESTAMP_SKEW.value
                ) from exc
            if exc.reason_code == REASON_SERVICE_ACCOUNT_MISSING:
                # 渠道没登记服务账号 → 产不出标准入站消息（③ 需要身份）。
                # 这是**渠道配置问题**，不是请求问题 —— 明确拒绝并说清怎么修。
                raise ChannelServiceAccountMissing(
                    str(exc),
                    code=ErrorCode.CHANNEL_SERVICE_ACCOUNT_MISSING.value,
                ) from exc
            raise WebhookSignatureInvalid(
                str(exc), code=ErrorCode.WEBHOOK_SIGNATURE_INVALID.value
            ) from exc
        except GatewayChannelNotFound as exc:
            raise ChannelNotFound(str(exc), code=ErrorCode.CHANNEL_NOT_FOUND.value) from exc
        except GatewayNormalizerMissing as exc:
            raise ChannelError(
                str(exc),
                code=ErrorCode.INBOUND_ADAPTER_MISSING.value,
            ) from exc

        message = accepted.message
        delivery = make_inbound_delivery(
            tenant_id=tenant_id,
            channel_id=channel_id,
            external_message_id=message.external_message_id,
            payload_summary={
                "external_user_id": message.external_user_id,
                "external_chat_id": message.external_chat_id,
                "text": message.text[:4096],
                "metadata": dict(message.raw_metadata),
            },
        )
        await self.delivery_repo.add(delivery)

        if self.publisher is not None:
            # ⚠️ 这里**不再打 G5 的点** —— 旧的 `ChannelMessageReceived` 事件已经
            # 没了，发出去的就是标准入站消息本身。
            await self.publisher.publish(
                message,
                tenant_id=tenant_id,
                workspace_id=channel.workspace_id,
                trace_id=message.trace_id or None,
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
                code=ErrorCode.CHANNEL_NOT_FOUND.value,
            )
        if channel.status is not ChannelStatus.ACTIVE:
            raise ChannelDisabled(
                f"channel {channel_id} is {channel.status.value}",
                code=ErrorCode.CHANNEL_DISABLED.value,
            )
        adapter = outbound_registry.get(channel.type)
        if adapter is None:
            raise ChannelError(
                f"no outbound adapter registered for channel type {channel.type.value}",
                code=ErrorCode.OUTBOUND_ADAPTER_MISSING.value,
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
                error_code=ErrorCode.CHANNEL_DELIVERY_FAILED.value,
            )
            await self.delivery_repo.update(failed)
            raise
        except Exception as exc:
            failed = delivery.with_status(DeliveryStatus.FAILED, error_code=type(exc).__name__)
            await self.delivery_repo.update(failed)
            raise ChannelDeliveryFailed(
                f"outbound send failed: {exc}",
                code=ErrorCode.CHANNEL_DELIVERY_FAILED.value,
            ) from exc
        else:
            return updated

    # ── ② Auth Identity ───────────────────────────────────────────────────

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
