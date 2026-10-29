"""③ Message Normalizer —— 端口与归一化上下文。

依据：``docs/refactor/session-architecture/gateway-refactor-plan.md`` §2.2 / §3.3
/ §9.1。

**③ 只做格式翻译**：协议 → 标准字段。它**不做任何文本改写**（不清洗、不截断、
不摘要），**不派生会话 key**（那是 Router 的事），**不决定 agent**（只透传
``explicit_agent_id``）。

**幂等键的原料在 ③ 采集、判定在 ④**（§2.3 的顺序规则 ③）：③ 产出
:class:`IdempotencyKey`（strong / weak + source），④ 负责落库与短路。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

from qzdap_agent_runtime.gateway.idempotency import (
    client_request_key,
    payload_fingerprint_key,
    platform_message_key,
)
from qzdap_agent_runtime.gateway.types import (
    ActorContext,
    ChannelCapabilities,
    ChannelType,
    IdempotencyKey,
    InboundMessage,
)

if TYPE_CHECKING:
    from collections.abc import Mapping
    from datetime import datetime
    from uuid import UUID


@dataclass(frozen=True, slots=True)
class NormalizerContext:
    """③ 的输入上下文 —— 由 ①② 提供。

    - ``actor`` 来自 ②（验签 / JWT 的结果）—— 归一化阶段**不再自己认身份**；
    - ``trace_id`` 来自 ①（传输层建立）—— 鉴权失败的请求也带得上；
    - ``capabilities`` 来自 ①（渠道注册表）—— 出站不再按 channel_type 硬判断；
    - ``external_chat_id`` 是**外部会话标识**（web 的 session_id）—— IM 的聊天 id
      在协议载荷里（适配器自己解），web 的在 URL 里（由 ① 放进来）。
    """

    actor: ActorContext
    channel_type: ChannelType
    trace_id: str
    channel_id: UUID | None = None
    external_chat_id: str | None = None
    capabilities: ChannelCapabilities = field(default_factory=ChannelCapabilities)


class MessageNormalizer(Protocol):
    """③ 的端口：把原始字节归一成 :class:`InboundMessage`。"""

    channel_type: ChannelType

    def normalize(
        self,
        *,
        body: bytes,
        headers: Mapping[str, str],
        context: NormalizerContext,
    ) -> InboundMessage: ...


def resolve_idempotency_key(
    *,
    client_request_id: str | None = None,
    external_message_id: str | None = None,
    channel: str,
    chat_id: str,
    user_id: str,
    text: str,
    now: datetime | None = None,
) -> IdempotencyKey:
    """按阶梯挑一把幂等键（§4.2）。

    ① 客户端显式 ``clientRequestId``（strong，24h）
    ② 平台原始事件 ID（strong，7d）—— IM 平台走这一档
    ③ 内容指纹（**weak**，120s）—— 兜底，**只记录不抑制**（决策 #5）

    **③ 只负责挑键，判定在 ④。**
    """
    if client_request_id:
        return client_request_key(client_request_id, now=now)
    if external_message_id:
        return platform_message_key(external_message_id, now=now)
    return payload_fingerprint_key(
        channel=channel,
        chat_id=chat_id,
        user_id=user_id,
        text=text,
        now=now,
    )


__all__ = ["MessageNormalizer", "NormalizerContext", "resolve_idempotency_key"]
