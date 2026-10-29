"""Gateway 标准数据契约（Gateway 方案 §4）。

四段流水线的产物：

- ① Channel Gateway → :class:`RawIngress`
- ② Auth Identity → :class:`AuthenticatedIngress`（含 :class:`ActorContext`）
- ③ Message Normalizer → :class:`InboundMessage`（含 :class:`IdempotencyKey`）
- ④ Idempotency Guard → :class:`IdempotencyDecision`

⚠️ **这些类型是 Gateway 与七层下游之间的唯一契约** —— 下游层全部只认这里定义的
字段，不各自解析入参（§0.1）。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID

# ---------------------------------------------------------------------------
# 枚举 / 字面量
# ---------------------------------------------------------------------------


class ChannelType(StrEnum):
    """入站渠道类型。"""

    WEB = "web"
    API = "api"
    FEISHU = "feishu"
    WECOM = "wecom"
    DINGTALK = "dingtalk"


class TrustLevel(StrEnum):
    """身份信任级别（② 判定）。"""

    VERIFIED_HMAC = "verified_hmac"
    JWT = "jwt"
    SIGNED_TOKEN = "signed_token"
    INTERNAL = "internal"


class AuthMethod(StrEnum):
    """取身份的方式（② 判定）。"""

    CHANNEL_SIGNATURE = "channel_signature"
    JWT = "jwt"
    API_KEY = "api_key"
    INTERNAL = "internal"


class KeySource(StrEnum):
    """幂等键来源（§4.2 的三级阶梯 + 审批决策）。"""

    CLIENT_REQUEST_ID = "client_request_id"
    PLATFORM_MESSAGE_ID = "platform_message_id"
    PAYLOAD_FINGERPRINT = "payload_fingerprint"
    # 审批决策 —— 平台为「某个待批工具调用的一次决策」生成的唯一 id。
    # 它是 strong：连点两次「同意」必须只执行一次工具（台账 G10）。
    APPROVAL_DECISION = "approval_decision"


KeyStrength = Literal["strong", "weak"]
IdempotencyOutcome = Literal["new", "duplicate", "in_progress", "taken_over"]


# ---------------------------------------------------------------------------
# ① RawIngress
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ChannelCapabilities:
    """渠道能力声明 —— 入站时就确定，出站不再按 channel_type 硬判断。"""

    streaming: bool = False
    cards: bool = False
    interactive: bool = False
    attachments: bool = False
    max_text_bytes: int = 4096
    max_attachments: int = 0


@dataclass(frozen=True, slots=True)
class RawIngress:
    """① Channel Gateway 的产物：还没验签、还没归一化的原始入站。"""

    transport: Literal["http", "sse", "webhook", "im"]
    channel_type: ChannelType
    channel_id: UUID | None
    capabilities: ChannelCapabilities
    method: str
    path: str
    headers: Mapping[str, str]
    body: bytes
    query: Mapping[str, str]
    trace_id: str
    peer: str | None = None
    ingress_ref: str | None = None


# ---------------------------------------------------------------------------
# ② AuthenticatedIngress
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ActorContext:
    """统一身份。web 是「已认证用户带租户头」，IM 是「平台签名证明的机器身份」。"""

    tenant_id: UUID
    workspace_id: UUID | None
    actor_id: UUID
    roles: tuple[str, ...] = ()
    actor_kind: Literal["user", "service_account"] = "user"


@dataclass(frozen=True, slots=True)
class AuthenticatedIngress:
    """② Auth Identity 的产物。"""

    raw: RawIngress
    actor: ActorContext
    trust: TrustLevel
    auth_method: AuthMethod
    auth_evidence: str


# ---------------------------------------------------------------------------
# ③ InboundMessage
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class IdempotencyKey:
    """幂等键。``strength`` 决定它是否参与判重（决策 #5）。"""

    value: str
    source: KeySource
    strength: KeyStrength
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class AttachmentRef:
    """附件统一模型（§4.4）。"""

    attachment_id: str
    filename: str
    content_type: str
    size_bytes: int
    sha256: str
    storage: Literal["db", "object_storage"]
    uri: str
    text_preview: str | None = None


@dataclass(frozen=True, slots=True)
class InboundMessage:
    """③ Message Normalizer 的产物 —— **下游七层唯一的入参契约**。"""

    actor: ActorContext
    channel_type: ChannelType
    channel_id: UUID | None
    external_chat_id: str
    external_user_id: str
    explicit_agent_id: UUID | None
    idempotency: IdempotencyKey
    external_message_id: str | None
    payload_hash: str
    trace_id: str
    text: str
    attachments: tuple[AttachmentRef, ...] = ()
    reply_to: str | None = None
    capabilities: ChannelCapabilities = field(default_factory=ChannelCapabilities)
    raw_metadata: Mapping[str, Any] = field(default_factory=dict)
    # 幂等键强度不足（weak）→ 本轮禁用有副作用的工具（决策 #5）。
    # 由 ③ 从 IdempotencyKey.strength 推出，④ 不再改写它。
    unprotected: bool = False


# ---------------------------------------------------------------------------
# ④ IdempotencyDecision
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class IdempotencyDecision:
    """④ Idempotency Guard 的判定结果。

    - ``new`` —— 首次到达，放行；
    - ``duplicate`` —— 命中同一把 strong 键，且原轮次已完成（可重放）；
    - ``in_progress`` —— 命中同一把 strong 键，但原轮次还在跑（重复请求）；
    - ``taken_over`` —— 命中的那一行已过期 → 当作不存在，重建（§4.4 过期分支）。
    """

    outcome: IdempotencyOutcome
    key_strength: KeyStrength
    row_id: UUID | None = None
    status: str | None = None
    turn_id: UUID | None = None
    expires_at: datetime | None = None

    @property
    def is_new(self) -> bool:
        return self.outcome == "new"

    @property
    def should_run(self) -> bool:
        """本轮是否应当执行 —— ``new`` 与 ``taken_over`` 都是「继续往下走」。"""
        return self.outcome in {"new", "taken_over"}

    @property
    def is_duplicate(self) -> bool:
        """重复 —— 调用方**不得**再跑一轮（重复请求 / 双击 / 网络重试）。"""
        return self.outcome in {"duplicate", "in_progress"}


__all__ = [
    "ActorContext",
    "AttachmentRef",
    "AuthMethod",
    "AuthenticatedIngress",
    "ChannelCapabilities",
    "ChannelType",
    "IdempotencyDecision",
    "IdempotencyKey",
    "IdempotencyOutcome",
    "InboundMessage",
    "KeySource",
    "KeyStrength",
    "RawIngress",
    "TrustLevel",
]
