"""Gateway 层 —— 入站四段流水线（① Channel Gateway → ② Auth → ③ Normalizer → ④ Idempotency）。

本包只放**契约**（数据类 + 端口），不放框架代码 —— 落库实现由 Session 侧提供。
"""

from __future__ import annotations

from qzdap_agent_runtime.gateway.channels import capabilities_for
from qzdap_agent_runtime.gateway.facade import (
    AcceptedIngress,
    ChannelDescriptor,
    ChannelDirectoryPort,
    Gateway,
    GatewayChannelNotFound,
    GatewayNormalizerMissing,
    scope_for,
)
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
from qzdap_agent_runtime.gateway.identity import (
    HmacWebhookVerifier,
    Identity,
    IdentityRejected,
    IdentityRequest,
    IdentityVerifier,
    InternalIdentityVerifier,
    JwtIdentityVerifier,
    ServiceAccount,
)
from qzdap_agent_runtime.gateway.normalizer import (
    MessageNormalizer,
    NormalizerContext,
    resolve_idempotency_key,
)
from qzdap_agent_runtime.gateway.outbound import (
    DeliveryOutcome,
    OutboundTarget,
    ResultSink,
)
from qzdap_agent_runtime.gateway.types import (
    ActorContext,
    AttachmentRef,
    AttachmentStoragePort,
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
    "AcceptedIngress",
    "ActorContext",
    "AttachmentRef",
    "AttachmentStoragePort",
    "AuthMethod",
    "AuthenticatedIngress",
    "ChannelCapabilities",
    "ChannelDescriptor",
    "ChannelDirectoryPort",
    "ChannelType",
    "DeliveryOutcome",
    "Gateway",
    "GatewayChannelNotFound",
    "GatewayNormalizerMissing",
    "HmacWebhookVerifier",
    "IdempotencyDecision",
    "IdempotencyGuard",
    "IdempotencyKey",
    "IdempotencyStore",
    "Identity",
    "IdentityRejected",
    "IdentityRequest",
    "IdentityVerifier",
    "InboundMessage",
    "InboxScope",
    "InternalIdentityVerifier",
    "JwtIdentityVerifier",
    "KeySource",
    "MessageNormalizer",
    "NormalizerContext",
    "OutboundTarget",
    "RawIngress",
    "ResultSink",
    "ServiceAccount",
    "TrustLevel",
    "approval_key",
    "capabilities_for",
    "client_request_key",
    "payload_fingerprint_key",
    "payload_hash_of",
    "platform_message_key",
    "resolve_idempotency_key",
    "scope_for",
]
