"""Web inbound adapter — accepts plaintext JSON webhooks.

Plain ``application/json`` envelope::

    {
        "external_user_id": "u1",
        "external_chat_id": "c1",
        "external_message_id": "m1",   # optional
        "text": "hello",
        "metadata": {}                  # optional, free-form
    }

Useful for browser chat widgets, curl smoke tests, and any system that
can sign a payload but doesn't fit a specific provider.
"""

from __future__ import annotations

import json
from typing import Any

from qzdap.modules.channel.application.ports import InboundAdapter, ParsedMessage
from qzdap.modules.channel.domain.value_objects import ChannelType


class WebInboundAdapter(InboundAdapter):
    channel_type = ChannelType.WEB

    def parse_webhook(
        self,
        *,
        body: bytes,
        headers: dict[str, str],
    ) -> ParsedMessage:
        payload = _safe_json(body)
        metadata = payload.get("metadata") or {}
        if not isinstance(metadata, dict):
            metadata = {"value": metadata}
        return ParsedMessage(
            external_user_id=str(payload.get("external_user_id", "")),
            external_chat_id=str(payload.get("external_chat_id", "")),
            external_message_id=payload.get("external_message_id"),
            text=str(payload.get("text", "")),
            metadata=metadata,
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


__all__ = ["WebInboundAdapter"]
