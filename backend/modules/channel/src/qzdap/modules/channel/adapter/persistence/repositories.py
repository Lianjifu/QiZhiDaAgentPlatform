"""SQL repositories — ChannelRepository / ChannelDeliveryRepository / WebhookSecretRepository."""

from __future__ import annotations

from datetime import UTC
from typing import TYPE_CHECKING

from sqlalchemy import select

from qzdap.modules.channel.adapter.persistence.models import (
    ChannelDeliveryORM,
    ChannelORM,
    ChannelSecretORM,
)
from qzdap.modules.channel.application.ports import (
    ChannelDeliveryRepository,
    ChannelRepository,
    WebhookSecretRepository,
)
from qzdap.modules.channel.domain.entities import Channel, ChannelDelivery
from qzdap.modules.channel.domain.value_objects import (
    ChannelStatus,
    ChannelType,
)
from qzdap_schema.ids import ChannelId, TenantId

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


def _channel_to_domain(row: ChannelORM) -> Channel:
    return Channel(
        id=ChannelId(row.id),
        tenant_id=TenantId(row.tenant_id),
        workspace_id=row.workspace_id,
        type=ChannelType(row.type),
        name=row.name,
        external_id=row.external_id,
        webhook_secret_id=row.webhook_secret_id,
        status=ChannelStatus(row.status),
        inbound_path=row.inbound_path,
        outbound_config=dict(row.outbound_config or {}),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _delivery_to_domain(row: ChannelDeliveryORM) -> ChannelDelivery:
    from qzdap.modules.channel.domain.value_objects import DeliveryStatus

    return ChannelDelivery(
        id=row.id,
        tenant_id=TenantId(row.tenant_id),
        channel_id=ChannelId(row.channel_id),
        direction=row.direction,
        external_message_id=row.external_message_id,
        session_id=row.session_id,
        payload_summary=dict(row.payload_summary or {}),
        status=DeliveryStatus(row.status),
        error_code=row.error_code,
        created_at=row.created_at,
        delivered_at=row.delivered_at,
    )


class SqlChannelRepository(ChannelRepository):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def add(self, channel: Channel) -> None:
        async with self._sf() as session:
            session.add(
                ChannelORM(
                    id=channel.id,
                    tenant_id=channel.tenant_id,
                    workspace_id=channel.workspace_id,
                    type=channel.type.value,
                    name=channel.name,
                    external_id=channel.external_id,
                    webhook_secret_id=channel.webhook_secret_id,
                    status=channel.status.value,
                    inbound_path=channel.inbound_path,
                    outbound_config=dict(channel.outbound_config),
                    created_at=channel.created_at,
                    updated_at=channel.updated_at,
                )
            )
            await session.commit()

    async def get(self, *, tenant_id: TenantId, channel_id: ChannelId) -> Channel | None:
        async with self._sf() as session:
            row = await session.get(ChannelORM, channel_id)
            if row is None or row.tenant_id != tenant_id:
                return None
            return _channel_to_domain(row)

    async def get_by_id(self, channel_id: ChannelId) -> Channel | None:
        """Tenant-agnostic lookup — used by webhook handlers that don't
        carry a tenant header. Tenant scoping is enforced by the HMAC
        secret + signature instead."""
        async with self._sf() as session:
            row = await session.get(ChannelORM, channel_id)
            if row is None:
                return None
            return _channel_to_domain(row)

    async def list(
        self,
        *,
        tenant_id: TenantId,
        workspace_id: UUID | None = None,
        enabled_only: bool = False,
        limit: int = 100,
    ) -> list[Channel]:
        async with self._sf() as session:
            stmt = select(ChannelORM).where(ChannelORM.tenant_id == tenant_id)
            if workspace_id is not None:
                stmt = stmt.where(
                    (ChannelORM.workspace_id.is_(None)) | (ChannelORM.workspace_id == workspace_id)
                )
            if enabled_only:
                stmt = stmt.where(ChannelORM.status == "active")
            stmt = stmt.limit(limit)
            rows = (await session.execute(stmt)).scalars().all()
            return [_channel_to_domain(r) for r in rows]

    async def update(self, channel: Channel) -> None:
        async with self._sf() as session:
            row = await session.get(ChannelORM, channel.id)
            if row is None or row.tenant_id != channel.tenant_id:
                return
            row.name = channel.name
            row.status = channel.status.value
            row.outbound_config = dict(channel.outbound_config)
            row.webhook_secret_id = channel.webhook_secret_id
            row.updated_at = channel.updated_at
            await session.commit()

    async def delete(self, *, tenant_id: TenantId, channel_id: ChannelId) -> bool:
        async with self._sf() as session:
            row = await session.get(ChannelORM, channel_id)
            if row is None or row.tenant_id != tenant_id:
                return False
            await session.delete(row)
            await session.commit()
            return True


class SqlChannelDeliveryRepository(ChannelDeliveryRepository):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def add(self, delivery: ChannelDelivery) -> None:
        async with self._sf() as session:
            session.add(
                ChannelDeliveryORM(
                    id=delivery.id,
                    tenant_id=delivery.tenant_id,
                    channel_id=delivery.channel_id,
                    direction=delivery.direction,
                    external_message_id=delivery.external_message_id,
                    session_id=delivery.session_id,
                    payload_summary=dict(delivery.payload_summary),
                    status=delivery.status.value,
                    error_code=delivery.error_code,
                    created_at=delivery.created_at,
                    delivered_at=delivery.delivered_at,
                )
            )
            await session.commit()

    async def get(self, *, tenant_id: TenantId, delivery_id: UUID) -> ChannelDelivery | None:
        async with self._sf() as session:
            row = await session.get(ChannelDeliveryORM, delivery_id)
            if row is None or row.tenant_id != tenant_id:
                return None
            return _delivery_to_domain(row)

    async def list_for_channel(
        self,
        *,
        tenant_id: TenantId,
        channel_id: ChannelId,
        limit: int = 50,
    ) -> list[ChannelDelivery]:
        async with self._sf() as session:
            stmt = (
                select(ChannelDeliveryORM)
                .where(
                    ChannelDeliveryORM.tenant_id == tenant_id,
                    ChannelDeliveryORM.channel_id == channel_id,
                )
                .order_by(ChannelDeliveryORM.created_at.desc())
                .limit(limit)
            )
            rows = (await session.execute(stmt)).scalars().all()
            return [_delivery_to_domain(r) for r in rows]

    async def update(self, delivery: ChannelDelivery) -> None:
        async with self._sf() as session:
            row = await session.get(ChannelDeliveryORM, delivery.id)
            if row is None or row.tenant_id != delivery.tenant_id:
                return
            row.status = delivery.status.value
            row.error_code = delivery.error_code
            row.external_message_id = delivery.external_message_id
            row.delivered_at = delivery.delivered_at
            await session.commit()


class SqlWebhookSecretRepository(WebhookSecretRepository):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def add(
        self,
        *,
        tenant_id: TenantId,
        channel_type: ChannelType,
        label: str,
        encrypted_payload: bytes,
        key_version: int = 1,
    ) -> UUID:
        from datetime import datetime

        async with self._sf() as session:
            row = ChannelSecretORM(
                tenant_id=tenant_id,
                channel_type=channel_type.value,
                label=label,
                encrypted_payload=encrypted_payload,
                key_version=key_version,
                created_at=datetime.now(UTC),
            )
            session.add(row)
            await session.commit()
            return row.id

    async def get(self, *, tenant_id: TenantId, secret_id: UUID) -> bytes | None:
        async with self._sf() as session:
            row = await session.get(ChannelSecretORM, secret_id)
            if row is None or row.tenant_id != tenant_id:
                return None
            return bytes(row.encrypted_payload)

    async def delete(self, *, tenant_id: TenantId, secret_id: UUID) -> bool:
        async with self._sf() as session:
            row = await session.get(ChannelSecretORM, secret_id)
            if row is None or row.tenant_id != tenant_id:
                return False
            await session.delete(row)
            await session.commit()
            return True


__all__ = [
    "SqlChannelDeliveryRepository",
    "SqlChannelRepository",
    "SqlWebhookSecretRepository",
]
