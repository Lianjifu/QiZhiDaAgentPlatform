"""Channel HTTP router — /v1/channels CRUD + /v1/channels/{cid}/webhook.

Auth + actor context is wired through ``request.state.actor`` (admin
role for mutations, any authenticated actor for webhook receive).
Inbound adapter registry + outbound adapter registry are read from
``app.state.channel_*_registry`` (set by the composition container).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Body, Path, Query, Request, status

from qzdap.modules.channel.adapter.http.dto import (
    ChannelListResponse,
    ChannelResponse,
    DeliveryResponse,
    RegisterChannelRequest,
    SendReplyRequest,
    UpdateChannelRequest,
)
from qzdap.modules.channel.adapter.http.mappers import (
    channel_list_to_response,
    channel_to_response,
    delivery_to_response,
)
from qzdap.modules.channel.domain.errors import ChannelNotFound
from qzdap.modules.channel.domain.value_objects import ChannelStatus, ChannelType
from qzdap_schema.ids import ChannelId, TenantId

if TYPE_CHECKING:
    from uuid import UUID

    from qzdap.modules.channel.application.ports import InboundAdapter, OutboundAdapter
    from qzdap.modules.channel.application.services import ChannelService

router = APIRouter(prefix="/v1", tags=["channel"])


def _make_channel_service(request: Request) -> ChannelService:
    svc = getattr(request.app.state, "channel_service", None)
    if svc is None:
        raise RuntimeError(
            "channel_service is not configured; composition container "
            "must set app.state.channel_service before serving"
        )
    return svc


def _inbound_registry(request: Request) -> dict[ChannelType, InboundAdapter]:
    reg = getattr(request.app.state, "channel_inbound_registry", None)
    if reg is None:
        raise RuntimeError("channel_inbound_registry not configured")
    return reg


def _outbound_registry(request: Request) -> dict[ChannelType, OutboundAdapter]:
    reg = getattr(request.app.state, "channel_outbound_registry", None)
    if reg is None:
        raise RuntimeError("channel_outbound_registry not configured")
    return reg


def _require_actor(request: Request):
    actor = getattr(request.state, "actor", None)
    if actor is None:
        raise RuntimeError(
            "actor not resolved; auth middleware must populate "
            "request.state.actor before this router runs"
        )
    return actor


def _require_admin(request: Request):
    actor = _require_actor(request)
    roles: frozenset[str] = getattr(actor, "roles", frozenset())  # type: ignore[attr-defined]
    if "admin" not in roles:
        from qzdap_kernel.errors import ForbiddenError

        raise ForbiddenError("admin role required", code="TENANT_DENIED")
    return actor


@router.post(
    "/channels",
    response_model=ChannelResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register_channel(
    request: Request,
    body: RegisterChannelRequest,
) -> ChannelResponse:
    svc = _make_channel_service(request)
    actor = _require_admin(request)
    ch = await svc.register_channel(
        tenant_id=TenantId(actor.tenant_id),
        workspace_id=body.workspace_id,
        type=ChannelType(body.type),
        name=body.name,
        external_id=body.external_id,
        inbound_path=body.inbound_path,
        webhook_secret=body.webhook_secret,
        outbound_config=body.outbound_config,
    )
    return channel_to_response(ch)


@router.get("/channels", response_model=ChannelListResponse)
async def list_channels(
    request: Request,
    enabled_only: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=500),
) -> ChannelListResponse:
    svc = _make_channel_service(request)
    actor = _require_actor(request)
    items = await svc.list_channels(
        tenant_id=TenantId(actor.tenant_id),
        workspace_id=actor.workspace_id,
        enabled_only=enabled_only,
        limit=limit,
    )
    return channel_list_to_response(items)


@router.get("/channels/{channel_id}", response_model=ChannelResponse)
async def get_channel(
    request: Request,
    channel_id: Annotated[UUID, Path()],
) -> ChannelResponse:
    svc = _make_channel_service(request)
    actor = _require_actor(request)
    ch = await svc.channel_repo.get(  # type: ignore[attr-defined]
        tenant_id=TenantId(actor.tenant_id), channel_id=ChannelId(channel_id)
    )
    if ch is None:
        raise ChannelNotFound(f"channel {channel_id} not found", code="CHANNEL_NOT_FOUND")
    return channel_to_response(ch)


@router.patch("/channels/{channel_id}", response_model=ChannelResponse)
async def update_channel(
    request: Request,
    channel_id: Annotated[UUID, Path()],
    body: UpdateChannelRequest,
) -> ChannelResponse:
    svc = _make_channel_service(request)
    actor = _require_admin(request)
    ch = await svc.channel_repo.get(  # type: ignore[attr-defined]
        tenant_id=TenantId(actor.tenant_id), channel_id=ChannelId(channel_id)
    )
    if ch is None:
        raise ChannelNotFound(f"channel {channel_id} not found", code="CHANNEL_NOT_FOUND")

    updated = ch
    if body.status is not None:
        updated = updated.with_status(ChannelStatus(body.status))
    if body.outbound_config is not None:
        updated = updated.with_outbound_config(body.outbound_config)
    if body.webhook_secret is not None:
        blob = svc.cipher.encrypt(body.webhook_secret.encode("utf-8"))
        new_sid = await svc.secret_repo.add(  # type: ignore[attr-defined]
            tenant_id=updated.tenant_id,
            channel_type=updated.type,
            label=f"{updated.name}.webhook.rotated",
            encrypted_payload=blob,
        )
        updated = updated.with_secret(new_sid)
    await svc.channel_repo.update(updated)  # type: ignore[attr-defined]
    return channel_to_response(updated)


@router.post(
    "/channels/{channel_id}/webhook",
    response_model=DeliveryResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def receive_webhook(
    request: Request,
    channel_id: Annotated[UUID, Path()],
) -> DeliveryResponse:
    """Inbound webhook entry — verifies signature, parses, persists delivery.

    Auth here is intentionally looser: the signature check IS the auth.
    A service-account actor is materialized from the verified channel
    so downstream handlers see a stable tenant_id.
    """
    svc = _make_channel_service(request)
    body_bytes = await request.body()
    headers = {k.lower(): v for k, v in request.headers.items()}
    ch = await svc.channel_repo.get_by_id(  # type: ignore[attr-defined]
        channel_id=ChannelId(channel_id)
    )
    if ch is None:
        raise ChannelNotFound(f"channel {channel_id} not found", code="CHANNEL_NOT_FOUND")
    delivery = await svc.handle_webhook(
        tenant_id=ch.tenant_id,
        channel_id=ChannelId(channel_id),
        body=body_bytes,
        headers=headers,
        inbound_registry=_inbound_registry(request),
    )
    return delivery_to_response(delivery)


@router.post(
    "/channels/{channel_id}/send",
    response_model=DeliveryResponse,
)
async def send_reply(
    request: Request,
    channel_id: Annotated[UUID, Path()],
    body: Annotated[SendReplyRequest, Body()],
) -> DeliveryResponse:
    svc = _make_channel_service(request)
    actor = _require_actor(request)
    delivery = await svc.send_reply(
        tenant_id=TenantId(actor.tenant_id),
        channel_id=ChannelId(channel_id),
        external_chat_id=body.external_chat_id,
        text=body.text,
        outbound_registry=_outbound_registry(request),
        metadata=body.metadata,
    )
    return delivery_to_response(delivery)


def _tenant_from_channel(_request: Request, _channel_id: UUID) -> TenantId:
    """Reserved — webhook tenant resolution now happens via
    ``channel_repo.get_by_id`` (no tenant filter) before signature
    verify. This helper stays for backward compat with any future
    multi-tenant dispatcher.
    """
    raise RuntimeError(
        "tenant-from-channel resolution deprecated; use ChannelService.handle_webhook"
    )


__all__ = [
    "get_channel",
    "list_channels",
    "receive_webhook",
    "register_channel",
    "router",
    "send_reply",
    "update_channel",
]
