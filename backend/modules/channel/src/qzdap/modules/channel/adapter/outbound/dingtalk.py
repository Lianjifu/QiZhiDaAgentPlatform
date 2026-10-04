"""DingTalk outbound adapter — robot group messages via webhook URL.

Two integration modes:

- **Custom robot** (``https://oapi.dingtalk.com/robot/send?access_token=...``)
  — requires the ``webhook_url`` in the channel's ``outbound_config``.
- **Enterprise app** (P10) — uses ``/robot/oToMessages/batchSend`` for
  targeted user/chat delivery. P6 ships the custom-robot path.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from qzdap.modules.channel.application.ports import OutboundAdapter
from qzdap.modules.channel.domain.errors import ChannelDeliveryFailed
from qzdap.modules.channel.domain.value_objects import ChannelType

if TYPE_CHECKING:
    import httpx


class DingTalkOutboundAdapter(OutboundAdapter):
    channel_type = ChannelType.DINGTALK

    def __init__(
        self,
        *,
        http: httpx.AsyncClient,
        webhook_url: str,
        request_timeout_seconds: float = 30.0,
    ) -> None:
        self._http = http
        self._webhook_url = webhook_url
        self._timeout = request_timeout_seconds

    async def send_reply(
        self,
        *,
        external_chat_id: str,
        text: str,
        metadata: dict[str, Any],
    ) -> str | None:
        at_mobiles = metadata.get("at_mobiles") or []
        payload: dict[str, Any] = {
            "msgtype": "text",
            "text": {"content": text},
            "chatid": external_chat_id or None,
        }
        if at_mobiles:
            payload["at"] = {"atMobiles": list(at_mobiles), "isAtAll": False}
        resp = await self._http.post(self._webhook_url, json=payload, timeout=self._timeout)
        if resp.status_code >= 400:
            raise ChannelDeliveryFailed(
                f"dingtalk send failed: {resp.status_code} {resp.text}",
                code="CHANNEL_DELIVERY_FAILED",
            )
        body = (
            resp.json()
            if resp.headers.get("content-type", "").startswith("application/json")
            else {}
        )
        if isinstance(body, dict) and body.get("errcode") not in (None, 0):
            raise ChannelDeliveryFailed(
                f"dingtalk send rejected: {body.get('errmsg', 'unknown')}",
                code="CHANNEL_DELIVERY_FAILED",
            )
        return None


__all__ = ["DingTalkOutboundAdapter"]
