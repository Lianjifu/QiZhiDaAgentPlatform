"""Feishu inbound adapter — parses Feishu Open Platform event envelope.

Feishu events arrive in two flavors:

1. **URL verification** (``type=url_verification``): the platform
   pings the webhook URL once on registration; we must echo the
   ``challenge`` field back. The signature verifier upstream allows
   this when ``X-Lark-Request-Timestamp`` and ``X-Lark-Signature``
   headers validate.
2. **Message events** (``header.event_type=im.message.received_v1``):
   the payload includes sender / message identifiers that we map to
   the standard :class:`InboundMessage`.

P6 scope: plaintext events only. Encrypted payloads (``event.encrypt``
with AES-decrypt of the symmetric key) land in P10.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from qzdap.modules.channel.adapter.inbound._base import (
    build_inbound_message,
    object_storage_attachment,
)
from qzdap_agent_runtime.gateway.types import (
    AttachmentRef,
    ChannelType,
    InboundMessage,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from qzdap_agent_runtime.gateway.normalizer import NormalizerContext


class FeishuInboundAdapter:
    """③ 的飞书实现 —— 产出标准 :class:`InboundMessage`。"""

    channel_type = ChannelType.FEISHU

    def normalize(
        self,
        *,
        body: bytes,
        headers: Mapping[str, str],
        context: NormalizerContext,
    ) -> InboundMessage:
        _ = headers
        payload = _safe_json(body)

        # URL verification handshake.
        if payload.get("type") == "url_verification":
            challenge = str(payload.get("challenge", ""))
            return build_inbound_message(
                context=context,
                body=body,
                external_user_id="feishu-verification",
                external_chat_id="feishu-verification",
                text=challenge,
                raw_metadata={"kind": "url_verification"},
            )

        event = payload.get("event") or {}
        sender = event.get("sender") or {}
        sender_id = sender.get("sender_id") or {}
        message = event.get("message") or {}
        message_id = message.get("message_id")
        chat_id = message.get("chat_id") or sender_id.get("chat_id") or ""
        user_id = sender_id.get("user_id") or sender_id.get("open_id") or ""
        message_type = str(message.get("message_type") or "text")

        # Feishu messages include a `content` JSON string; for plain text
        # it's `{"text": "..."}`. Other types (post / image / file) are
        # represented as **附件**（统一形状），文本部分照常抽取。
        content = _decode_content(message.get("content"))
        text = str(content.get("text") or "")
        attachments = _attachments(message_type, content)

        return build_inbound_message(
            context=context,
            body=body,
            external_user_id=str(user_id),
            external_chat_id=str(chat_id),
            external_message_id=str(message_id) if message_id else None,
            text=text,
            attachments=attachments,
            raw_metadata={
                "message_type": message_type,
                "chat_type": event.get("chat_type", "p2p"),
                "tenant_key": event.get("tenant_key", ""),
                "raw_event_type": (payload.get("header") or {}).get("event_type", ""),
            },
        )


def _safe_json(body: bytes) -> dict[str, Any]:
    if not body:
        return {}
    try:
        decoded = json.loads(body)
    except json.JSONDecodeError:
        return {}
    if not isinstance(decoded, dict):
        return {}
    return decoded


def _decode_content(content: Any) -> dict[str, Any]:
    """飞书的 ``content`` 是**一个 JSON 字符串** —— 解不开就当纯文本。"""
    if content is None:
        return {}
    if isinstance(content, dict):
        return content
    if isinstance(content, str):
        try:
            decoded = json.loads(content)
        except json.JSONDecodeError:
            return {"text": content}
        if isinstance(decoded, dict):
            return decoded
        return {"text": content}
    return {"text": str(content)}


def _attachments(message_type: str, content: dict[str, Any]) -> tuple[AttachmentRef, ...]:
    """图片 / 文件 / 音视频 → 统一成 :class:`AttachmentRef`（§3.4）。

    **字节不在这里** —— 飞书的图片要另走 image_key 下载接口。
    """
    if message_type == "image":
        key = str(content.get("image_key") or "")
        if not key:
            return ()
        return (
            object_storage_attachment(
                attachment_id=key,
                filename="",
                content_type="image/*",
                uri=key,
            ),
        )
    if message_type in {"file", "audio", "media"}:
        key = str(content.get("file_key") or "")
        if not key:
            return ()
        return (
            object_storage_attachment(
                attachment_id=key,
                filename=str(content.get("file_name") or ""),
                content_type=str(content.get("file_type") or "application/octet-stream"),
                uri=key,
            ),
        )
    return ()


__all__ = ["FeishuInboundAdapter"]
