"""Inbound adapters — translate raw webhook envelopes into ``InboundMessage``.

Each adapter implements ``MessageNormalizer`` (the Gateway ③ port) and is
registered in a dict keyed by ``ChannelType``. The HTTP router resolves
the adapter per-channel and hands the standard message to
``ChannelService``.

⚠️ **五个入口，一个形状** —— web / api / 飞书 / 企微 / 钉钉归一化后除
``channel_type`` / ``raw_metadata`` 外字段完全一致（§10 Stage 3 验收）。
"""

from __future__ import annotations

from qzdap.modules.channel.adapter.inbound.api import ApiInboundAdapter
from qzdap.modules.channel.adapter.inbound.dingtalk import DingTalkInboundAdapter
from qzdap.modules.channel.adapter.inbound.feishu import FeishuInboundAdapter
from qzdap.modules.channel.adapter.inbound.web import WebInboundAdapter
from qzdap.modules.channel.adapter.inbound.wechatwork import WeChatWorkInboundAdapter

__all__ = [
    "ApiInboundAdapter",
    "DingTalkInboundAdapter",
    "FeishuInboundAdapter",
    "WeChatWorkInboundAdapter",
    "WebInboundAdapter",
]
