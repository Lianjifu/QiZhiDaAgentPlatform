"""Channel 协议层：ChannelMessage 入站 DTO + ResultSink 出站分发。"""

from __future__ import annotations

from .gateway import (
    ChannelMessage,
    build_session_key,
    build_trace_id,
    payload_hash,
)

# ResultSink 协议在 Stage 5 实现；本文件先只暴露 Channel 入站侧。
__all__ = [
    "ChannelMessage",
    "build_session_key",
    "build_trace_id",
    "payload_hash",
]