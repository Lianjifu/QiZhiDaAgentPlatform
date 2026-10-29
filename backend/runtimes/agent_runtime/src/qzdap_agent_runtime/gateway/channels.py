"""① Channel Gateway —— 渠道注册表与**能力声明**。

依据：``docs/refactor/session-architecture/gateway-refactor-plan.md`` §2.2 / §3.5。

**能力在入站时就确定**（§3.5）：渠道支不支持卡片 / 交互 / 流式，不再由出站
按 ``channel_type`` 硬判断 —— 那是旧实现的做法，能力散落在各处 if。
"""

from __future__ import annotations

from types import MappingProxyType

from qzdap_agent_runtime.gateway.types import ChannelCapabilities, ChannelType

_CAPABILITIES: MappingProxyType[ChannelType, ChannelCapabilities] = MappingProxyType(
    {
        ChannelType.WEB: ChannelCapabilities(
            streaming=True,
            cards=False,
            interactive=False,
            attachments=True,
            max_text_bytes=4096,
            max_attachments=10,
        ),
        ChannelType.API: ChannelCapabilities(
            streaming=True,
            cards=False,
            interactive=False,
            attachments=True,
            max_text_bytes=16384,
            max_attachments=10,
        ),
        ChannelType.FEISHU: ChannelCapabilities(
            streaming=False,
            cards=True,
            interactive=True,
            attachments=True,
            max_text_bytes=4096,
            max_attachments=10,
        ),
        ChannelType.WECHATWORK: ChannelCapabilities(
            streaming=False,
            cards=True,
            interactive=True,
            attachments=True,
            max_text_bytes=4096,
            max_attachments=10,
        ),
        ChannelType.DINGTALK: ChannelCapabilities(
            streaming=False,
            cards=True,
            interactive=False,
            attachments=True,
            max_text_bytes=4096,
            max_attachments=10,
        ),
    }
)

_FALLBACK = ChannelCapabilities()


def capabilities_for(channel_type: ChannelType) -> ChannelCapabilities:
    """该渠道的能力声明 —— 未知渠道给最保守的一份。"""
    return _CAPABILITIES.get(channel_type, _FALLBACK)


__all__ = ["capabilities_for"]
