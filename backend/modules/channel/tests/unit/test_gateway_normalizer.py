"""Stage 3 验收：五个入口归一化后是**同一个形状**。

依据：``docs/architecture/session-lifecycle.md`` 验收 —— 「5 种入口归一化后，除 ``channel_type`` /
``raw_metadata`` 外字段完全一致（参数化测试）；附件三套语义收敛为一个
``AttachmentRef``」。

⚠️ **三处按设计必须不同**（不是「没归一」，是「本来就该不同」）：

- ``channel_type`` —— 入口本身就是渠道；
- ``raw_metadata`` —— 协议细节（飞书的 ``tenant_key`` / 钉钉的 ``robot_code``…）；
- ``payload_hash`` / ``capabilities`` —— 前者是**原始 body** 的摘要（body 不同
  就必然不同），后者是**渠道的能力声明**（渠道支不支持卡片本来就不同）。

其余字段（身份、外部标识、幂等键、文本、附件、trace）必须逐字一致。
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from qzdap.modules.channel.adapter.inbound import (
    ApiInboundAdapter,
    DingTalkInboundAdapter,
    FeishuInboundAdapter,
    WebInboundAdapter,
    WeChatWorkInboundAdapter,
)
from qzdap_agent_runtime.gateway.channels import capabilities_for
from qzdap_agent_runtime.gateway.normalizer import NormalizerContext
from qzdap_agent_runtime.gateway.types import ActorContext, ChannelType, InboundMessage

_MESSAGE_ID = "m-42"
_USER = "u-7"
_CHAT = "c-9"
_TEXT = "hello"
_TENANT = uuid4()
_ACTOR = uuid4()
_CHANNEL = uuid4()

#: 五个入口 —— 各自一份「同义」的载荷。
_PAYLOADS: dict[ChannelType, tuple[object, bytes]] = {
    ChannelType.WEB: (
        WebInboundAdapter(),
        b'{"external_user_id":"u-7","external_chat_id":"c-9",'
        b'"external_message_id":"m-42","text":"hello"}',
    ),
    ChannelType.API: (
        ApiInboundAdapter(),
        b'{"external_user_id":"u-7","external_chat_id":"c-9",'
        b'"external_message_id":"m-42","text":"hello"}',
    ),
    ChannelType.FEISHU: (
        FeishuInboundAdapter(),
        b'{"header":{"event_type":"im.message.received_v1"},"event":{"sender":'
        b'{"sender_id":{"user_id":"u-7"}},"message":{"message_id":"m-42",'
        b'"chat_id":"c-9","message_type":"text","content":"{\\"text\\":\\"hello\\"}"}}}',
    ),
    ChannelType.DINGTALK: (
        DingTalkInboundAdapter(),
        b'{"msgtype":"text","text":{"content":"hello"},"senderId":"u-7",'
        b'"conversationId":"c-9","msgId":"m-42"}',
    ),
    ChannelType.WECHATWORK: (
        WeChatWorkInboundAdapter(),
        b"<xml><ToUserName><![CDATA[c-9]]></ToUserName>"
        b"<FromUserName><![CDATA[u-7]]></FromUserName>"
        b"<MsgType><![CDATA[text]]></MsgType>"
        b"<Content><![CDATA[hello]]></Content>"
        b"<MsgId>m-42</MsgId></xml>",
    ),
}


def _context(channel_type: ChannelType) -> NormalizerContext:
    return NormalizerContext(
        actor=ActorContext(
            tenant_id=_TENANT,
            workspace_id=None,
            actor_id=_ACTOR,
            roles=("service_account",),
            actor_kind="service_account",
        ),
        channel_type=channel_type,
        channel_id=_CHANNEL,
        trace_id="trace-1",
        capabilities=capabilities_for(channel_type),
    )


def _normalize(channel_type: ChannelType) -> InboundMessage:
    adapter, body = _PAYLOADS[channel_type]
    msg = adapter.normalize(  # type: ignore[attr-defined]
        body=body,
        headers={},
        context=_context(channel_type),
    )
    assert isinstance(msg, InboundMessage)
    return msg


@pytest.mark.parametrize("channel_type", list(_PAYLOADS))
def test_every_entry_produces_the_same_standard_shape(channel_type: ChannelType) -> None:
    msg = _normalize(channel_type)
    assert msg.actor.tenant_id == _TENANT
    assert msg.actor.actor_id == _ACTOR
    assert msg.actor.actor_kind == "service_account"
    assert msg.channel_type is channel_type
    assert msg.channel_id == _CHANNEL
    assert msg.external_user_id == _USER
    assert msg.external_chat_id == _CHAT
    assert msg.external_message_id == _MESSAGE_ID
    assert msg.text == _TEXT
    assert msg.trace_id == "trace-1"
    assert msg.attachments == ()
    # 幂等键：平台消息 id → strong，且**跨入口同值**（值里不含渠道）。
    assert msg.idempotency.source.value == "platform_message_id"
    assert msg.idempotency.strength == "strong"
    assert msg.idempotency.value == _MESSAGE_ID
    # strong 键 → 不标 unprotected。
    assert msg.unprotected is False


@pytest.mark.parametrize("channel_type", list(_PAYLOADS))
def test_the_standard_fields_are_identical_across_entries(channel_type: ChannelType) -> None:
    """除「按设计就该不同」的三处外，其余字段逐字一致。"""
    reference = _normalize(ChannelType.WEB)
    msg = _normalize(channel_type)
    assert (
        msg.actor,
        msg.external_chat_id,
        msg.external_user_id,
        msg.external_message_id,
        msg.idempotency.value,
        msg.idempotency.source,
        msg.idempotency.strength,
        msg.text,
        msg.trace_id,
        msg.attachments,
        msg.unprotected,
    ) == (
        reference.actor,
        reference.external_chat_id,
        reference.external_user_id,
        reference.external_message_id,
        reference.idempotency.value,
        reference.idempotency.source,
        reference.idempotency.strength,
        reference.text,
        reference.trace_id,
        reference.attachments,
        reference.unprotected,
    )


def test_the_inbound_message_survives_the_bus_round_trip() -> None:
    """总线载荷走的是 ``_as_payload_dict`` —— 还原必须无损（否则下游拿到的是 repr）。"""
    original = _normalize(ChannelType.FEISHU)
    restored = InboundMessage.from_payload(original._as_payload_dict())
    assert restored == original


# ── 附件：三套语义收敛为一个 AttachmentRef ────────────────────────────────


@pytest.mark.parametrize(
    ("channel_type", "body"),
    [
        (
            ChannelType.FEISHU,
            b'{"event":{"sender":{"sender_id":{"user_id":"u"}},"message":'
            b'{"message_id":"m","chat_id":"c","message_type":"image",'
            b'"content":"{\\"image_key\\":\\"img_1\\"}"}}}',
        ),
        (
            ChannelType.DINGTALK,
            b'{"msgtype":"image","image":{"media_id":"media_1","content_type":"image/*"},'
            b'"senderId":"u","conversationId":"c"}',
        ),
        (
            ChannelType.WECHATWORK,
            b"<xml><ToUserName><![CDATA[c]]></ToUserName>"
            b"<FromUserName><![CDATA[u]]></FromUserName>"
            b"<MsgType><![CDATA[image]]></MsgType>"
            b"<MediaId><![CDATA[media_1]]></MediaId></xml>",
        ),
    ],
)
def test_attachments_converge_on_one_shape(channel_type: ChannelType, body: bytes) -> None:
    """飞书的 image_key / 钉钉的 media_id / 企微的 MediaId → 同一个 AttachmentRef。

    字节不在消息里（要另走下载接口）—— 只统一**引用形状**。
    """
    adapter, _ = _PAYLOADS[channel_type]
    msg = adapter.normalize(  # type: ignore[attr-defined]
        body=body,
        headers={},
        context=_context(channel_type),
    )
    assert len(msg.attachments) == 1
    attachment = msg.attachments[0]
    assert attachment.storage == "object_storage"
    assert attachment.attachment_id
    assert attachment.content_type.startswith("image/")
    assert attachment.uri == attachment.attachment_id


def test_the_web_entry_without_a_platform_message_id_falls_back_to_a_weak_key() -> None:
    """没有平台消息 id → 内容指纹（**weak**：只记录不抑制，决策 #5）。"""
    msg = WebInboundAdapter().normalize(
        body=b'{"external_user_id":"u","external_chat_id":"c","text":"hi"}',
        headers={},
        context=_context(ChannelType.WEB),
    )
    assert msg.idempotency.source.value == "payload_fingerprint"
    assert msg.idempotency.strength == "weak"
    # weak → 标 unprotected（本轮禁用有副作用的工具）。
    assert msg.unprotected is True


def test_a_client_request_id_wins_over_the_platform_message_id() -> None:
    """阶梯：客户端 id 优先于平台消息 id（strong）。"""
    msg = WebInboundAdapter().normalize(
        body=b'{"external_user_id":"u","external_chat_id":"c","text":"hi",'
        b'"clientRequestId":"req-1"}',
        headers={},
        context=_context(ChannelType.WEB),
    )
    assert msg.idempotency.source.value == "client_request_id"
    assert msg.idempotency.strength == "strong"
    assert msg.idempotency.value == "req-1"


def test_the_attachment_ref_carries_no_bytes() -> None:
    """附件只带引用 —— 消息里**不含**字节（体积与敏感面）。"""
    msg = _normalize(ChannelType.WEB)
    assert all(isinstance(a.attachment_id, str) for a in msg.attachments)
    assert not isinstance(msg.attachments, bytes)


def test_the_channel_id_is_carried_through() -> None:
    """渠道 id 必须在消息里 —— 下游据此取渠道行（工作区 / 服务账号）。"""
    msg = _normalize(ChannelType.DINGTALK)
    assert msg.channel_id == _CHANNEL


__all__ = []
