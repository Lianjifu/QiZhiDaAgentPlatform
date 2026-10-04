"""Outbound adapters — send replies via channel provider APIs.

P6 implementation strategy: each adapter wraps a single ``send_reply``
call against the provider's Open API and caches its auth token in
process. The container wires one ``httpx.AsyncClient`` per app and
hands it to each adapter.
"""

from __future__ import annotations

from qzdap.modules.channel.adapter.outbound.dingtalk import DingTalkOutboundAdapter
from qzdap.modules.channel.adapter.outbound.feishu import FeishuOutboundAdapter
from qzdap.modules.channel.adapter.outbound.web import WebOutboundAdapter
from qzdap.modules.channel.adapter.outbound.wechatwork import WeChatWorkOutboundAdapter

__all__ = [
    "DingTalkOutboundAdapter",
    "FeishuOutboundAdapter",
    "WeChatWorkOutboundAdapter",
    "WebOutboundAdapter",
]
