"""Gateway 层 —— 入站四段流水线（① Channel Gateway → ② Auth → ③ Normalizer → ④ Idempotency）。

本包只放**契约**（数据类 + 端口），不放框架代码 —— 落库实现由 Session 侧提供。
"""

from __future__ import annotations

from qzdap_agent_runtime.gateway.idempotency import (
    IdempotencyGuard,
    IdempotencyStore,
    InboxScope,
    approval_key,
    client_request_key,
    payload_fingerprint_key,
    payload_hash_of,
    platform_message_key,
)
from qzdap_agent_runtime.gateway.types import (
    ActorContext,
    AttachmentRef,
    AuthenticatedIngress,
    AuthMethod,
    ChannelCapabilities,
    ChannelType,
    IdempotencyDecision,
    IdempotencyKey,
    InboundMessage,
    KeySource,
    RawIngress,
    TrustLevel,
)

__all__ = [
    "ActorContext",
    "AttachmentRef",
    "AuthMethod",
    "AuthenticatedIngress",
    "ChannelCapabilities",
    "ChannelType",
    "IdempotencyDecision",
    "IdempotencyGuard",
    "IdempotencyKey",
    "IdempotencyStore",
    "InboundMessage",
    "InboxScope",
    "KeySource",
    "RawIngress",
    "TrustLevel",
    "approval_key",
    "client_request_key",
    "payload_fingerprint_key",
    "payload_hash_of",
    "platform_message_key",
]
