"""入站适配器的公共装配（③ Message Normalizer 的共用部分）。

**为什么有这一层**：四个 IM 适配器各自解析协议细节，但「装配成
:class:`InboundMessage`」的形状是**同一件事** —— 幂等键的挑选、载荷指纹、
``unprotected`` 的推导、附件的归一，都在这里做一次，避免四份实现各写一遍
（写四遍 = 四个实现 = 迟早漂移）。
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING, Any

from qzdap_agent_runtime.gateway.normalizer import resolve_idempotency_key
from qzdap_agent_runtime.gateway.types import (
    AttachmentRef,
    InboundMessage,
)

if TYPE_CHECKING:
    from collections.abc import Mapping
    from uuid import UUID

    from qzdap_agent_runtime.gateway.normalizer import NormalizerContext


def payload_hash(body: bytes) -> str:
    """原始载荷的 sha256 —— 审计与排查用（不泄露内容）。"""
    return hashlib.sha256(body or b"").hexdigest()


def build_inbound_message(
    *,
    context: NormalizerContext,
    body: bytes,
    external_user_id: str,
    external_chat_id: str,
    external_message_id: str | None = None,
    text: str = "",
    attachments: tuple[AttachmentRef, ...] = (),
    raw_metadata: Mapping[str, Any] | None = None,
    explicit_agent_id: UUID | None = None,
    client_request_id: str | None = None,
    reply_to: str | None = None,
) -> InboundMessage:
    """装配标准入站消息。

    **幂等键**：按阶梯挑（客户端 id → 平台消息 id → 内容指纹）；**指纹是 weak**，
    只记录不抑制（决策 #5）。``unprotected`` 由键强度推出 —— weak 的那一轮
    **禁用有副作用的工具**。
    """
    key = resolve_idempotency_key(
        client_request_id=client_request_id,
        external_message_id=external_message_id,
        channel=str(context.channel_type),
        chat_id=external_chat_id,
        user_id=external_user_id,
        text=text,
    )
    return InboundMessage(
        actor=context.actor,
        channel_type=context.channel_type,
        channel_id=context.channel_id,
        external_chat_id=external_chat_id,
        external_user_id=external_user_id,
        explicit_agent_id=explicit_agent_id,
        idempotency=key,
        external_message_id=external_message_id,
        payload_hash=payload_hash(body),
        trace_id=context.trace_id,
        text=text,
        attachments=attachments,
        reply_to=reply_to,
        capabilities=context.capabilities,
        raw_metadata=dict(raw_metadata or {}),
        unprotected=key.strength == "weak",
    )


def object_storage_attachment(
    *,
    attachment_id: str,
    filename: str,
    content_type: str,
    uri: str,
    text_preview: str | None = None,
) -> AttachmentRef:
    """平台侧附件（飞书 file_key / 企微 MediaId / 钉钉 media_id）的统一形状。

    **字节不在这里** —— 平台侧附件要另走平台的下载接口；这里只统一**形状**
    （§3.4：本次不迁对象存储）。
    """
    return AttachmentRef(
        attachment_id=attachment_id,
        filename=filename,
        content_type=content_type,
        size_bytes=0,
        sha256="",
        storage="object_storage",
        uri=uri,
        text_preview=text_preview,
    )


__all__ = [
    "build_inbound_message",
    "object_storage_attachment",
    "payload_hash",
]
