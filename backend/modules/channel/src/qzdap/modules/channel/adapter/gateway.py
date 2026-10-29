"""① Channel Gateway 的渠道目录 —— Gateway 端口的**渠道侧实现**。

Gateway 需要「渠道实体查询」（用哪把密钥、属于哪个租户、登记了哪个服务账号），
这通过端口 :class:`ChannelDirectoryPort` 实现，**实现在渠道模块侧** ——
Gateway 不反向依赖渠道模块（§9.2.1 的依赖方向）。

返回的是**裁剪过的视图**（:class:`ChannelDescriptor`）：只带验签与身份需要的
东西，不把渠道实体整个交出去。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from qzdap_agent_runtime.gateway.facade import ChannelDescriptor
from qzdap_agent_runtime.gateway.identity import ServiceAccount
from qzdap_schema.ids import ChannelId

if TYPE_CHECKING:
    from uuid import UUID

    from qzdap.modules.channel.application.ports import (
        ChannelRepository,
        WebhookSecretCipher,
        WebhookSecretRepository,
    )


class ChannelDirectoryAdapter:
    """按渠道 id 取出鉴权材料与归属。"""

    def __init__(
        self,
        *,
        channel_repo: ChannelRepository,
        secret_repo: WebhookSecretRepository,
        cipher: WebhookSecretCipher,
    ) -> None:
        self._channels = channel_repo
        self._secrets = secret_repo
        self._cipher = cipher

    async def get(self, channel_id: UUID) -> ChannelDescriptor | None:
        channel = await self._channels.get_by_id(ChannelId(channel_id))
        if channel is None:
            return None
        secret = b""
        if channel.webhook_secret_id is not None:
            blob = await self._secrets.get(
                tenant_id=channel.tenant_id,
                secret_id=channel.webhook_secret_id,
            )
            if blob is not None:
                secret = self._cipher.decrypt(blob)
        return ChannelDescriptor(
            channel_id=channel.id,
            channel_type=channel.type,
            tenant_id=channel.tenant_id,
            workspace_id=channel.workspace_id,
            secret=secret,
            service_account=ServiceAccount.from_mapping(channel.service_account),
        )


__all__ = ["ChannelDirectoryAdapter"]
