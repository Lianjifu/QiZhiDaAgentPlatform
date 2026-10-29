"""API inbound adapter — the platform's own HTTP API envelope.

Same JSON shape as the web adapter (:class:`WebInboundAdapter`), but a
distinct channel type: ``api`` callers are the platform's own clients
(machine-to-machine), not a browser widget.

Registered under :attr:`ChannelType.API` so that the five inbound entries
(web / api / feishu / wechatwork / dingtalk) normalize into **one**
standard shape (§10 Stage 3 验收).
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from qzdap.modules.channel.adapter.inbound._base import build_inbound_message
from qzdap_agent_runtime.gateway.types import ChannelType, InboundMessage

if TYPE_CHECKING:
    from collections.abc import Mapping

    from qzdap_agent_runtime.gateway.normalizer import NormalizerContext


class ApiInboundAdapter:
    """③ 的 api 实现 —— 产出标准 :class:`InboundMessage`。"""

    channel_type = ChannelType.API

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


__all__ = ["ApiInboundAdapter"]
