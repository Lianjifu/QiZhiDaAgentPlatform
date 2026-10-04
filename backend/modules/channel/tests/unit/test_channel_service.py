"""Channel domain + application tests.

Cover:
- Channel factory validation
- ChannelDelivery state transitions
- ChannelService.handle_webhook signature verify (HMAC + skew)
- ChannelService.send_reply happy path
- WebhookSignatureInvalid / WebhookTimestampSkew errors

Adapters (inbound/outbound, SQL, crypto) live in adapter/ and have
their own integration tests in step 7.
"""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

import pytest

# ── Test doubles (shared fixture) ─────────────────────────────────────────
from _channel_in_memory import (  # type: ignore[import-not-found]
    CollectingPublisher,
    FixedClock,
    InMemoryChannelRepo,
    InMemoryDeliveryRepo,
    InMemorySecretRepo,
    NoopCipher,
    SequenceIds,
)

from qzdap.modules.channel.application.ports import (
    InboundAdapter,
    OutboundAdapter,
    ParsedMessage,
    WebhookSecretCipher,
)
from qzdap.modules.channel.application.services import (
    DEFAULT_TIMESTAMP_TOLERANCE_SECONDS,
    ChannelService,
)
from qzdap.modules.channel.domain.entities import (
    make_channel,
    make_inbound_delivery,
)
from qzdap.modules.channel.domain.errors import (
    ChannelDeliveryFailed,
    ChannelDisabled,
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
from qzdap_schema.ids import ChannelId, TenantId


@dataclass(slots=True)
class EchoInbound(InboundAdapter):
    channel_type: ChannelType = ChannelType.WEB

    def parse_webhook(self, *, body: bytes, headers: dict[str, str]) -> ParsedMessage:
        import json

        payload = json.loads(body or b"{}")
        return ParsedMessage(
            external_user_id=str(payload.get("external_user_id", "u1")),
            external_chat_id=str(payload.get("external_chat_id", "c1")),
            external_message_id=payload.get("external_message_id"),
            text=str(payload.get("text", "")),
            metadata={"raw_headers": dict(headers)},
        )


@dataclass(slots=True)
class RecordingOutbound(OutboundAdapter):
    channel_type: ChannelType = ChannelType.WEB
    sent: list[dict[str, Any]] = field(default_factory=list)
    fail: bool = False
    return_id: str | None = "out-1"

    async def send_reply(self, *, external_chat_id, text, metadata):
        self.sent.append(
            {"external_chat_id": external_chat_id, "text": text, "metadata": dict(metadata)}
        )
        if self.fail:
            raise ChannelDeliveryFailed(
                "synthetic outbound failure", code="CHANNEL_DELIVERY_FAILED"
            )
        return self.return_id


def _make_service(
    *,
    publisher=None,
    clock: FixedClock | None = None,
    cipher: WebhookSecretCipher | None = None,
    tolerance: int | None = None,
) -> tuple[
    ChannelService,
    InMemoryChannelRepo,
    InMemoryDeliveryRepo,
    InMemorySecretRepo,
    CollectingPublisher,
]:
    channel_repo = InMemoryChannelRepo()
    delivery_repo = InMemoryDeliveryRepo()
    secret_repo = InMemorySecretRepo()
    pub = publisher if publisher is not None else CollectingPublisher()
    svc = ChannelService(
        channel_repo=channel_repo,
        delivery_repo=delivery_repo,
        secret_repo=secret_repo,
        cipher=cipher or NoopCipher(),
        clock=clock or FixedClock(),
        ids=SequenceIds(),
        publisher=pub,
        default_timestamp_tolerance_seconds=tolerance or DEFAULT_TIMESTAMP_TOLERANCE_SECONDS,
    )
    return svc, channel_repo, delivery_repo, secret_repo, pub


# ── domain factory tests ──────────────────────────────────────────────────


def test_make_channel_validates_name() -> None:
    tenant = TenantId(uuid4())
    with pytest.raises(ValueError, match="non-empty"):
        make_channel(
            tenant_id=tenant,
            type=ChannelType.WEB,
            name="",
            external_id="e1",
            inbound_path="/hook",
        )


def test_make_channel_validates_external_id() -> None:
    tenant = TenantId(uuid4())
    with pytest.raises(ValueError, match="non-empty"):
        make_channel(
            tenant_id=tenant,
            type=ChannelType.WEB,
            name="ok",
            external_id="",
            inbound_path="/hook",
        )


def test_make_channel_validates_inbound_path() -> None:
    tenant = TenantId(uuid4())
    with pytest.raises(ValueError, match="start with"):
        make_channel(
            tenant_id=tenant,
            type=ChannelType.WEB,
            name="ok",
            external_id="e1",
            inbound_path="hook",
        )


def test_channel_with_status_returns_new_instance() -> None:
    tenant = TenantId(uuid4())
    ch = make_channel(
        tenant_id=tenant,
        type=ChannelType.WEB,
        name="c1",
        external_id="e1",
        inbound_path="/hook",
    )
    assert ch.status is ChannelStatus.ACTIVE
    disabled = ch.with_status(ChannelStatus.DISABLED)
    assert disabled.status is ChannelStatus.DISABLED
    assert ch.status is ChannelStatus.ACTIVE
    assert disabled.updated_at >= ch.updated_at


def test_channel_delivery_with_status_records_delivered_at() -> None:
    tenant = TenantId(uuid4())
    cid = ChannelId(uuid4())
    delivery = make_inbound_delivery(
        tenant_id=tenant,
        channel_id=cid,
        external_message_id="m1",
        payload_summary={"text": "hi"},
    )
    assert delivery.status is DeliveryStatus.PENDING
    assert delivery.delivered_at is None
    sent = delivery.with_status(DeliveryStatus.SENT)
    assert sent.delivered_at is not None


def test_make_inbound_delivery_rejects_none_summary() -> None:
    with pytest.raises(ValueError):
        make_inbound_delivery(
            tenant_id=TenantId(uuid4()),
            channel_id=ChannelId(uuid4()),
            external_message_id=None,
            payload_summary=None,  # type: ignore[arg-type]
        )


# ── service tests: registration ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_register_channel_with_secret() -> None:
    svc, channel_repo, _, secret_repo, _ = _make_service()
    tenant = TenantId(uuid4())
    ch = await svc.register_channel(
        tenant_id=tenant,
        workspace_id=None,
        type=ChannelType.WEB,
        name="webhook-1",
        external_id="ext-1",
        inbound_path="/hook/1",
        webhook_secret="supersecret",
    )
    assert ch.id in channel_repo.rows
    assert ch.webhook_secret_id is not None
    raw = await secret_repo.get(tenant_id=tenant, secret_id=ch.webhook_secret_id)
    assert raw is not None
    assert raw == b"ENC:supersecret"  # NoopCipher marker


@pytest.mark.asyncio
async def test_register_channel_without_secret() -> None:
    svc, _channel_repo, _, _, _ = _make_service()
    tenant = TenantId(uuid4())
    ch = await svc.register_channel(
        tenant_id=tenant,
        workspace_id=None,
        type=ChannelType.WEB,
        name="webhook-2",
        external_id="ext-2",
        inbound_path="/hook/2",
    )
    assert ch.webhook_secret_id is None


# ── service tests: webhook verification ───────────────────────────────────


def _sign(secret: bytes, ts: int, body: bytes) -> str:
    return hmac.new(secret, f"{ts}.".encode() + body, hashlib.sha256).hexdigest()


@pytest.mark.asyncio
async def test_handle_webhook_happy_path() -> None:
    cipher = NoopCipher()
    svc, _channel_repo, _delivery_repo, _secret_repo, publisher = _make_service(cipher=cipher)
    tenant = TenantId(uuid4())
    ch = await svc.register_channel(
        tenant_id=tenant,
        workspace_id=None,
        type=ChannelType.WEB,
        name="c1",
        external_id="e1",
        inbound_path="/hook",
        webhook_secret="topsecret",
    )
    body = b'{"external_user_id":"u1","external_chat_id":"c1","text":"hello"}'
    ts = int(svc.clock.now().timestamp())
    sig = _sign(b"topsecret", ts, body)
    delivery = await svc.handle_webhook(
        tenant_id=tenant,
        channel_id=ch.id,
        body=body,
        headers={
            "X-Webhook-Timestamp": str(ts),
            "X-Webhook-Signature": f"sha256={sig}",
        },
        inbound_registry={ChannelType.WEB: EchoInbound()},
    )
    assert delivery.status is DeliveryStatus.PENDING
    assert delivery.payload_summary["text"] == "hello"
    assert delivery.payload_summary["external_user_id"] == "u1"
    # publisher saw the message.received event
    topics = [t for t, _ in publisher.events]
    assert "channel.message.received" in topics


@pytest.mark.asyncio
async def test_handle_webhook_rejects_bad_signature() -> None:
    svc, _channel_repo, _delivery_repo, _, publisher = _make_service()
    tenant = TenantId(uuid4())
    ch = await svc.register_channel(
        tenant_id=tenant,
        workspace_id=None,
        type=ChannelType.WEB,
        name="c2",
        external_id="e2",
        inbound_path="/hook",
        webhook_secret="secret",
    )
    body = b'{"text":"hello"}'
    ts = int(svc.clock.now().timestamp())
    with pytest.raises(WebhookSignatureInvalid):
        await svc.handle_webhook(
            tenant_id=tenant,
            channel_id=ch.id,
            body=body,
            headers={
                "X-Webhook-Timestamp": str(ts),
                "X-Webhook-Signature": "sha256=deadbeef",
            },
            inbound_registry={ChannelType.WEB: EchoInbound()},
        )
    # publisher recorded the reject event
    topics = [t for t, _ in publisher.events]
    assert "channel.webhook.rejected" in topics


@pytest.mark.asyncio
async def test_handle_webhook_rejects_timestamp_skew() -> None:
    svc, _, _, _, _publisher = _make_service()
    tenant = TenantId(uuid4())
    ch = await svc.register_channel(
        tenant_id=tenant,
        workspace_id=None,
        type=ChannelType.WEB,
        name="c3",
        external_id="e3",
        inbound_path="/hook",
        webhook_secret="secret",
    )
    body = b'{"text":"hi"}'
    skew_ts = int(svc.clock.now().timestamp()) - 3600  # 1 hour skew
    sig = _sign(b"secret", skew_ts, body)
    with pytest.raises(WebhookTimestampSkew):
        await svc.handle_webhook(
            tenant_id=tenant,
            channel_id=ch.id,
            body=body,
            headers={
                "X-Webhook-Timestamp": str(skew_ts),
                "X-Webhook-Signature": f"sha256={sig}",
            },
            inbound_registry={ChannelType.WEB: EchoInbound()},
        )


@pytest.mark.asyncio
async def test_handle_webhook_rejects_missing_headers() -> None:
    svc, _, _, _, _ = _make_service()
    tenant = TenantId(uuid4())
    ch = await svc.register_channel(
        tenant_id=tenant,
        workspace_id=None,
        type=ChannelType.WEB,
        name="c4",
        external_id="e4",
        inbound_path="/hook",
        webhook_secret="secret",
    )
    body = b'{"text":"hi"}'
    with pytest.raises(WebhookSignatureInvalid):
        await svc.handle_webhook(
            tenant_id=tenant,
            channel_id=ch.id,
            body=body,
            headers={},
            inbound_registry={ChannelType.WEB: EchoInbound()},
        )


@pytest.mark.asyncio
async def test_handle_webhook_rejects_disabled_channel() -> None:
    svc, _, _, _, _ = _make_service()
    tenant = TenantId(uuid4())
    ch = await svc.register_channel(
        tenant_id=tenant,
        workspace_id=None,
        type=ChannelType.WEB,
        name="c5",
        external_id="e5",
        inbound_path="/hook",
        webhook_secret="secret",
    )
    await svc.set_status(
        tenant_id=tenant,
        channel_id=ch.id,
        status=ChannelStatus.DISABLED,
    )
    body = b'{"text":"hi"}'
    ts = int(svc.clock.now().timestamp())
    sig = _sign(b"secret", ts, body)
    with pytest.raises(ChannelDisabled):
        await svc.handle_webhook(
            tenant_id=tenant,
            channel_id=ch.id,
            body=body,
            headers={
                "X-Webhook-Timestamp": str(ts),
                "X-Webhook-Signature": f"sha256={sig}",
            },
            inbound_registry={ChannelType.WEB: EchoInbound()},
        )


@pytest.mark.asyncio
async def test_handle_webhook_unknown_channel() -> None:
    svc, _, _, _, _ = _make_service()
    with pytest.raises(ChannelNotFound):
        await svc.handle_webhook(
            tenant_id=TenantId(uuid4()),
            channel_id=ChannelId(uuid4()),
            body=b"{}",
            headers={},
            inbound_registry={ChannelType.WEB: EchoInbound()},
        )


# ── service tests: send_reply ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_send_reply_happy_path() -> None:
    svc, _, _, _, publisher = _make_service()
    tenant = TenantId(uuid4())
    ch = await svc.register_channel(
        tenant_id=tenant,
        workspace_id=None,
        type=ChannelType.WEB,
        name="c6",
        external_id="e6",
        inbound_path="/hook",
    )
    out = RecordingOutbound(channel_type=ChannelType.WEB)
    delivery = await svc.send_reply(
        tenant_id=tenant,
        channel_id=ch.id,
        external_chat_id="c-1",
        text="world",
        outbound_registry={ChannelType.WEB: out},
    )
    assert delivery.status is DeliveryStatus.SENT
    assert delivery.external_message_id == "out-1"
    assert out.sent == [{"external_chat_id": "c-1", "text": "world", "metadata": {}}]
    topics = [t for t, _ in publisher.events]
    assert "channel.reply.sent" in topics


@pytest.mark.asyncio
async def test_send_reply_records_failure() -> None:
    svc, _, delivery_repo, _, _ = _make_service()
    tenant = TenantId(uuid4())
    ch = await svc.register_channel(
        tenant_id=tenant,
        workspace_id=None,
        type=ChannelType.WEB,
        name="c7",
        external_id="e7",
        inbound_path="/hook",
    )
    out = RecordingOutbound(channel_type=ChannelType.WEB, fail=True)
    with pytest.raises(ChannelDeliveryFailed):
        await svc.send_reply(
            tenant_id=tenant,
            channel_id=ch.id,
            external_chat_id="c-2",
            text="boom",
            outbound_registry={ChannelType.WEB: out},
        )
    # the failed delivery row exists with status=FAILED
    failed = [d for d in delivery_repo.rows.values() if d.status is DeliveryStatus.FAILED]
    assert len(failed) == 1
    assert failed[0].error_code == "CHANNEL_DELIVERY_FAILED"


@pytest.mark.asyncio
async def test_send_reply_unknown_channel() -> None:
    svc, _, _, _, _ = _make_service()
    with pytest.raises(ChannelNotFound):
        await svc.send_reply(
            tenant_id=TenantId(uuid4()),
            channel_id=ChannelId(uuid4()),
            external_chat_id="c",
            text="hi",
            outbound_registry={ChannelType.WEB: RecordingOutbound(channel_type=ChannelType.WEB)},
        )


# ── list / disable ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_channels_filters() -> None:
    svc, _, _, _, _ = _make_service()
    tenant = TenantId(uuid4())
    a = await svc.register_channel(
        tenant_id=tenant,
        workspace_id=None,
        type=ChannelType.WEB,
        name="a",
        external_id="ea",
        inbound_path="/a",
    )
    b = await svc.register_channel(
        tenant_id=tenant,
        workspace_id=None,
        type=ChannelType.WEB,
        name="b",
        external_id="eb",
        inbound_path="/b",
    )
    await svc.set_status(tenant_id=tenant, channel_id=b.id, status=ChannelStatus.DISABLED)
    items = await svc.list_channels(tenant_id=tenant)
    assert len(items) == 2
    enabled = await svc.list_channels(tenant_id=tenant, enabled_only=True)
    assert {c.id for c in enabled} == {a.id}


# ── event payload shape ───────────────────────────────────────────────────


def test_event_payloads_are_dicts() -> None:
    tenant = TenantId(uuid4())
    cid = ChannelId(uuid4())
    msg = ChannelMessageReceived(
        channel_id=cid,
        channel_type="web",
        external_user_id="u1",
        external_chat_id="c1",
        text_preview="hello",
        tenant_id=tenant,
    )
    assert msg.to_payload()["channel_type"] == "web"
    reply = ChannelReplySent(
        channel_id=cid,
        delivery_id=uuid4(),
        external_chat_id="c1",
        tenant_id=tenant,
    )
    assert reply.TOPIC == "channel.reply.sent"
    rej = ChannelWebhookRejected(
        channel_id=cid,
        reason_code="BAD_SIGNATURE",
        tenant_id=tenant,
    )
    assert rej.TOPIC == "channel.webhook.rejected"
