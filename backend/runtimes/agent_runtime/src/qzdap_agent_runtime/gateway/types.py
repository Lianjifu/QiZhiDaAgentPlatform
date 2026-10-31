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

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Literal, Protocol
from uuid import UUID

from qzdap_kernel.events import DomainEvent

if TYPE_CHECKING:
    from collections.abc import Mapping

# ---------------------------------------------------------------------------
# 枚举 / 字面量
# ---------------------------------------------------------------------------


class ChannelType(StrEnum):
    """入站渠道类型。"""

    WEB = "web"
    API = "api"
    FEISHU = "feishu"
    WECHATWORK = "wechatwork"
    DINGTALK = "dingtalk"


class TrustLevel(StrEnum):
    """身份信任级别（② 判定）。"""

    VERIFIED_HMAC = "verified_hmac"
    JWT = "jwt"
    SIGNED_TOKEN = "signed_token"  # noqa: S105 —— 事件类型名 ✓ 不是口令 ✓
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
class InboundMessage(DomainEvent):
    """③ Message Normalizer 的产物 —— **下游七层唯一的入参契约**。

    它同时是**总线事件**：入站消息被受理后，标准化后的形状就是发到总线上的
    东西（取代旧的 ``ChannelMessageReceived``）。

    ⚠️ **总线按类名路由**（``EventEnvelope.event_name`` = 类名），因此订阅方
    要按 ``"InboundMessage"`` 订阅 —— **不是** dotted 的 topic 串。按 topic 串
    订阅是旧实现的一个真实缺陷：它让整条 IM 入站链路**从未被触发过**。
    """

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

    # ── 总线载荷 ───────────────────────────────────────────────────────
    # ⚠️ 方法名必须是 ``_as_payload_dict`` —— ``EventEnvelope.wrap`` 只认它
    # （旧实现写的是 ``to_payload``，**从未被调用**，slots dataclass 的事件
    # 因此退化成了 ``{"value": "<repr>"}``）。

    def _as_payload_dict(self) -> dict[str, Any]:
        return {
            "actor": {
                "tenant_id": str(self.actor.tenant_id),
                "workspace_id": (str(self.actor.workspace_id) if self.actor.workspace_id else None),
                "actor_id": str(self.actor.actor_id),
                "roles": list(self.actor.roles),
                "actor_kind": self.actor.actor_kind,
            },
            "channel_type": str(self.channel_type),
            "channel_id": str(self.channel_id) if self.channel_id else None,
            "external_chat_id": self.external_chat_id,
            "external_user_id": self.external_user_id,
            "explicit_agent_id": (str(self.explicit_agent_id) if self.explicit_agent_id else None),
            "idempotency": {
                "value": self.idempotency.value,
                "source": str(self.idempotency.source),
                "strength": self.idempotency.strength,
                "expires_at": self.idempotency.expires_at.isoformat(),
            },
            "external_message_id": self.external_message_id,
            "payload_hash": self.payload_hash,
            "trace_id": self.trace_id,
            "text": self.text,
            "attachments": [
                {
                    "attachment_id": item.attachment_id,
                    "filename": item.filename,
                    "content_type": item.content_type,
                    "size_bytes": item.size_bytes,
                    "sha256": item.sha256,
                    "storage": item.storage,
                    "uri": item.uri,
                    "text_preview": item.text_preview,
                }
                for item in self.attachments
            ],
            "reply_to": self.reply_to,
            "capabilities": {
                "streaming": self.capabilities.streaming,
                "cards": self.capabilities.cards,
                "interactive": self.capabilities.interactive,
                "attachments": self.capabilities.attachments,
                "max_text_bytes": self.capabilities.max_text_bytes,
                "max_attachments": self.capabilities.max_attachments,
            },
            "raw_metadata": dict(self.raw_metadata),
            "unprotected": self.unprotected,
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> InboundMessage:
        """从总线载荷还原 —— 与 :meth:`_as_payload_dict` 互为逆运算。"""
        actor_raw = payload.get("actor") or {}
        idem_raw = payload.get("idempotency") or {}
        caps_raw = payload.get("capabilities") or {}
        workspace_raw = actor_raw.get("workspace_id")
        channel_raw = payload.get("channel_id")
        explicit_raw = payload.get("explicit_agent_id")
        return cls(
            actor=ActorContext(
                tenant_id=UUID(str(actor_raw["tenant_id"])),
                workspace_id=UUID(str(workspace_raw)) if workspace_raw else None,
                actor_id=UUID(str(actor_raw["actor_id"])),
                roles=tuple(str(r) for r in (actor_raw.get("roles") or ())),
                actor_kind=str(actor_raw.get("actor_kind") or "user"),
            ),
            channel_type=ChannelType(str(payload.get("channel_type") or "web")),
            channel_id=UUID(str(channel_raw)) if channel_raw else None,
            external_chat_id=str(payload.get("external_chat_id") or ""),
            external_user_id=str(payload.get("external_user_id") or ""),
            explicit_agent_id=UUID(str(explicit_raw)) if explicit_raw else None,
            idempotency=IdempotencyKey(
                value=str(idem_raw.get("value") or ""),
                source=KeySource(str(idem_raw.get("source") or "payload_fingerprint")),
                strength=str(idem_raw.get("strength") or "weak"),
                expires_at=datetime.fromisoformat(str(idem_raw["expires_at"])),
            ),
            external_message_id=(
                str(payload["external_message_id"]) if payload.get("external_message_id") else None
            ),
            payload_hash=str(payload.get("payload_hash") or ""),
            trace_id=str(payload.get("trace_id") or ""),
            text=str(payload.get("text") or ""),
            attachments=tuple(
                AttachmentRef(
                    attachment_id=str(item.get("attachment_id") or ""),
                    filename=str(item.get("filename") or ""),
                    content_type=str(item.get("content_type") or ""),
                    size_bytes=int(item.get("size_bytes") or 0),
                    sha256=str(item.get("sha256") or ""),
                    storage=str(item.get("storage") or "db"),
                    uri=str(item.get("uri") or ""),
                    text_preview=item.get("text_preview"),
                )
                for item in (payload.get("attachments") or ())
            ),
            reply_to=(str(payload["reply_to"]) if payload.get("reply_to") else None),
            capabilities=ChannelCapabilities(
                streaming=bool(caps_raw.get("streaming")),
                cards=bool(caps_raw.get("cards")),
                interactive=bool(caps_raw.get("interactive")),
                attachments=bool(caps_raw.get("attachments")),
                max_text_bytes=int(caps_raw.get("max_text_bytes") or 4096),
                max_attachments=int(caps_raw.get("max_attachments") or 0),
            ),
            raw_metadata=dict(payload.get("raw_metadata") or {}),
            unprotected=bool(payload.get("unprotected")),
        )


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


class AttachmentStoragePort(Protocol):
    """附件字节的读取端口（§3.4）。

    **本次不迁字节到对象存储** —— 只统一形状并抽出端口。平台侧的附件
    （飞书/企微/钉钉的 file_key）用 ``storage="object_storage"`` + ``uri``
    表示；平台内上传的附件用 ``storage="db"`` + ``uri=附件 id``。
    """

    async def read(self, ref: AttachmentRef) -> bytes:
        """读出附件字节 —— 引用不存在或无权访问时抛异常。"""
        ...


__all__ = [
    "ActorContext",
    "AttachmentRef",
    "AttachmentStoragePort",
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
