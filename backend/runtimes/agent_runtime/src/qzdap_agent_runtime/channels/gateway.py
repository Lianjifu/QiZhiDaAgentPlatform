"""Channel 入站规范化 DTO (§5.1)。

ChannelMessage 是渠道入站事件的统一表示，由各 IM / webhook adapter
在验签 + 落 session_inbox 后产出。Session key 由 tenant + workspace +
channel + external_chat + external_user 组成；trace_id 必须从 IM 平台
webhook header 提取（飞书 X-Trace-Id / 企微 ReqParam.Trace-Id /
钉钉 eventId），无则生成 UUIDv5。
"""

from __future__ import annotations

import hashlib
import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# 用于生成 trace_id 的 UUIDv5 namespace；保持稳定，避免不同运行间漂移。
_TRACE_NAMESPACE = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")


class ChannelMessage(BaseModel):
    """渠道入站规范化 DTO（§5.1）。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    # 租户/工作区维度
    tenant_id: str
    workspace_id: str
    channel_id: str
    channel_type: str  # "web" | "api" | "webhook" | "feishu" | "wecom" | "dingtalk" | ...

    # 外部会话与用户维度
    external_chat_id: str
    external_user_id: str
    external_message_id: str  # IM 平台原始事件 ID，跨系统去重

    # Trace 维度
    trace_id: str | None = None  # 优先取自 webhook header；无则自动生成
    original_event_id: str | None = None  # IM 平台原始事件 ID，用于跨系统去重

    # 文本与附件
    text: str
    attachments: list[dict[str, Any]] = Field(default_factory=list)

    # 原始 metadata（保留以备审计）
    raw_metadata: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def build_trace_id(channel_id: str, original_event_id: str) -> str:
    """实现 §5.1 "无则生成 UUIDv5" 约定。"""
    return str(uuid.uuid5(_TRACE_NAMESPACE, f"{channel_id}:{original_event_id}"))


def payload_hash(payload: dict[str, Any]) -> str:
    """实现 §4.2 `session_inbox.payload_hash` 字段：原始 payload 的 sha256。"""
    import json

    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_session_key(
    tenant_id: str,
    workspace_id: str,
    channel_id: str,
    external_chat_id: str,
    external_user_id: str,
) -> str:
    """实现 §5.1 "Session key 由租户、工作区、渠道、外部会话和外部用户组成"。

    返回的 key 形如 `{tenant}:{workspace}:{channel}:{chat}:{user}`，
    所有组件均做最低限度清洗（去除冒号），避免 channel adapter
    各自定义临时会话（§2 中提到的问题）。
    """
    parts = [tenant_id, workspace_id, channel_id, external_chat_id, external_user_id]
    sanitized = [p.replace(":", "_") for p in parts]
    return ":".join(sanitized)


__all__ = [
    "ChannelMessage",
    "build_session_key",
    "build_trace_id",
    "payload_hash",
]