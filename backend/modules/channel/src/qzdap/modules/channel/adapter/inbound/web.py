"""Web inbound adapter — accepts plaintext JSON webhooks.

Plain ``application/json`` envelope::

    {
        "external_user_id": "u1",
        "external_chat_id": "c1",
        "external_message_id": "m1",   # optional
        "clientRequestId": "r1",       # optional — strong 幂等键
        "text": "hello",
        "metadata": {}                  # optional, free-form
    }

Useful for browser chat widgets, curl smoke tests, and any system that
can sign a payload but doesn't fit a specific provider.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from qzdap.modules.channel.adapter.inbound._base import build_inbound_message
from qzdap_agent_runtime.gateway.types import ChannelType, InboundMessage

if TYPE_CHECKING:
    from collections.abc import Mapping

    from qzdap_agent_runtime.gateway.normalizer import NormalizerContext


class WebInboundAdapter:
    """③ 的 web 实现 —— 产出标准 :class:`InboundMessage`。"""

    channel_type = ChannelType.WEB

    def normalize(
        self,
        *,
        body: bytes,
        headers: Mapping[str, str],
        context: NormalizerContext,
    ) -> InboundMessage:
        _ = headers
        payload = _safe_json(body)
        metadata = payload.get("metadata") or {}
        if not isinstance(metadata, dict):
            metadata = {"value": metadata}
        client_request_id = str(payload.get("clientRequestId") or "")
        return build_inbound_message(
            context=context,
            body=body,
            external_user_id=str(payload.get("external_user_id", "")),
            external_chat_id=str(payload.get("external_chat_id", "")),
            external_message_id=_opt_str(payload.get("external_message_id")),
            text=str(payload.get("text", "")),
            raw_metadata=metadata,
            client_request_id=client_request_id or None,
        )


def _opt_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


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
