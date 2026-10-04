"""Feishu inbound adapter — parses Feishu Open Platform event envelope.

Feishu events arrive in two flavors:

1. **URL verification** (``type=url_verification``): the platform
   pings the webhook URL once on registration; we must echo the
   ``challenge`` field back. The signature verifier upstream allows
   this when ``X-Lark-Request-Timestamp`` and ``X-Lark-Signature``
   headers validate.
2. **Message events** (``header.event_type=im.message.received_v1``):
   the payload includes sender / message identifiers that we map to
   ``ParsedMessage``.

P6 scope: plaintext events only. Encrypted payloads (``event.encrypt``
with AES-decrypt of the symmetric key) land in P10.
"""

from __future__ import annotations

import json
from typing import Any

from qzdap.modules.channel.application.ports import InboundAdapter, ParsedMessage
from qzdap.modules.channel.domain.value_objects import ChannelType


class FeishuInboundAdapter(InboundAdapter):
    channel_type = ChannelType.FEISHU

    def parse_webhook(
        self,
        *,
        body: bytes,
        headers: dict[str, str],
    ) -> ParsedMessage:
        payload = _safe_json(body)

        # URL verification handshake.
        if payload.get("type") == "url_verification":
            challenge = str(payload.get("challenge", ""))
            return ParsedMessage(
                external_user_id="feishu-verification",
                external_chat_id="feishu-verification",
                external_message_id=None,
                text=challenge,
                metadata={"kind": "url_verification"},
            )

        event = payload.get("event") or {}
        sender = event.get("sender") or {}
        sender_id = sender.get("sender_id") or {}
        message = event.get("message") or {}
        message_id = message.get("message_id")
        chat_id = message.get("chat_id") or sender_id.get("chat_id") or ""
        user_id = sender_id.get("user_id") or sender_id.get("open_id") or ""

        # Feishu messages include a `content` JSON string; for plain text
        # it's `{"text": "..."}`. Other types (post / image / file) are
        # represented as opaque markers so the agent can decide what to
        # do.
        text = _extract_text(message.get("content"))

        return ParsedMessage(
            external_user_id=str(user_id),
            external_chat_id=str(chat_id),
            external_message_id=str(message_id) if message_id else None,
            text=text,
            metadata={
                "message_type": message.get("message_type", "text"),
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


def _extract_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        try:
            decoded = json.loads(content)
        except json.JSONDecodeError:
            return content
        if isinstance(decoded, dict):
            return str(decoded.get("text", ""))
        return content
    if isinstance(content, dict):
        return str(content.get("text", ""))
    return str(content)


__all__ = ["FeishuInboundAdapter"]
