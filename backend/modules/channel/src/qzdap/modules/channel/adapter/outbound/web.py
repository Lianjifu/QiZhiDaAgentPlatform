"""Web outbound adapter — POSTs replies to a configured webhook URL.

The web channel's ``outbound_config`` must include ``webhook_url``. The
adapter POSTs a JSON envelope to that URL and surfaces a delivery
failure if the response status is not 2xx.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from qzdap.modules.channel.application.ports import OutboundAdapter
from qzdap.modules.channel.domain.errors import ChannelDeliveryFailed
from qzdap.modules.channel.domain.value_objects import ChannelType

if TYPE_CHECKING:
    import httpx


class WebOutboundAdapter(OutboundAdapter):
    channel_type = ChannelType.WEB

    def __init__(
        self,
        *,
        http: httpx.AsyncClient,
        webhook_url: str | None = None,
        request_timeout_seconds: float = 30.0,
    ) -> None:
        self._http = http
        self._webhook_url = webhook_url
        self._timeout = request_timeout_seconds

    def set_webhook_url(self, url: str) -> None:
        """Hot-swap the webhook URL — used by the container after the
        channel row is registered."""
        self._webhook_url = url

    async def send_reply(
        self,
        *,
        external_chat_id: str,
        text: str,
        metadata: dict[str, Any],
    ) -> str | None:
        if not self._webhook_url:
            raise ChannelDeliveryFailed(
                "web outbound has no webhook_url configured",
                code="CHANNEL_DELIVERY_FAILED",
            )
        resp = await self._http.post(
            self._webhook_url,
            json={
                "external_chat_id": external_chat_id,
                "text": text,
                "metadata": metadata,
            },
            timeout=self._timeout,
        )
        if resp.status_code >= 400:
            raise ChannelDeliveryFailed(
                f"web webhook returned {resp.status_code}",
                code="CHANNEL_DELIVERY_FAILED",
            )
        try:
            body = resp.json()
        except Exception:
            return None
        if isinstance(body, dict):
            return body.get("external_message_id")
        return None


__all__ = ["WebOutboundAdapter"]
