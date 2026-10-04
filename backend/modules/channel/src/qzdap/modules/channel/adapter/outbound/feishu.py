"""Feishu outbound adapter — POST /open-apis/im/v1/messages.

Uses ``tenant_access_token`` cached in-process; ``/auth/v3/tenant_access_token/internal``
returns a 2-hour token. P6: simple LRU with 90-min TTL.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from qzdap.modules.channel.application.ports import OutboundAdapter
from qzdap.modules.channel.domain.errors import ChannelDeliveryFailed
from qzdap.modules.channel.domain.value_objects import ChannelType

if TYPE_CHECKING:
    import httpx


class FeishuOutboundAdapter(OutboundAdapter):
    channel_type = ChannelType.FEISHU

    BASE_URL = "https://open.feishu.cn/open-apis"
    TOKEN_TTL_SECONDS = 5400  # 90 min — under the 2-hour server limit

    def __init__(
        self,
        *,
        http: httpx.AsyncClient,
        app_id: str,
        app_secret: str,
        request_timeout_seconds: float = 30.0,
    ) -> None:
        self._http = http
        self._app_id = app_id
        self._app_secret = app_secret
        self._timeout = request_timeout_seconds
        self._cached_token: str | None = None
        self._token_expiry: float = 0.0

    async def _token(self) -> str:
        if self._cached_token and time.monotonic() < self._token_expiry:
            return self._cached_token
        resp = await self._http.post(
            f"{self.BASE_URL}/auth/v3/tenant_access_token/internal",
            json={"app_id": self._app_id, "app_secret": self._app_secret},
            timeout=self._timeout,
        )
        resp.raise_for_status()
        body = resp.json()
        if body.get("code") != 0:
            raise ChannelDeliveryFailed(
                f"feishu auth failed: {body.get('msg', 'unknown')}",
                code="CHANNEL_DELIVERY_FAILED",
            )
        token = body["tenant_access_token"]
        self._cached_token = token
        self._token_expiry = time.monotonic() + self.TOKEN_TTL_SECONDS
        return token

    async def send_reply(
        self,
        *,
        external_chat_id: str,
        text: str,
        metadata: dict[str, Any],
    ) -> str | None:
        token = await self._token()
        msg_type = str(metadata.get("msg_type", "text"))
        receive_id_type = str(metadata.get("receive_id_type", "chat_id"))
        content = {"text": text}
        resp = await self._http.post(
            f"{self.BASE_URL}/im/v1/messages",
            params={"receive_id_type": receive_id_type},
            headers={"Authorization": f"Bearer {token}"},
            json={
                "receive_id": external_chat_id,
                "msg_type": msg_type,
                "content": json_dumps(content),
            },
            timeout=self._timeout,
        )
        if resp.status_code >= 400:
            raise ChannelDeliveryFailed(
                f"feishu send failed: {resp.status_code} {resp.text}",
                code="CHANNEL_DELIVERY_FAILED",
            )
        body = resp.json()
        if body.get("code") != 0:
            raise ChannelDeliveryFailed(
                f"feishu send rejected: {body.get('msg', 'unknown')}",
                code="CHANNEL_DELIVERY_FAILED",
            )
        return body.get("data", {}).get("message_id")


def json_dumps(obj: Any) -> str:
    import json

    return json.dumps(obj, ensure_ascii=False)


__all__ = ["FeishuOutboundAdapter"]
