"""web / api 入口的 ② 与 ③ —— 身份与归一化。

依据：``docs/architecture/session-lifecycle.md``
（web 的信任模型）、§3.3（标准入站数据）。

**web 的信任模型（§3.2）**：**已认证用户 + 租户头**。

⚠️ **租户由客户端头自证** —— 这是 web 的**既有约定**，不是本层能改的（那是
Auth 层的债：§1.1 的「身份有两套来源」缺陷）。本层只做**归一**：把
「principal / 租户头 / 会话 id / 请求体」翻译成**一份标准入站消息**，让下游
七层只认这一种形状。

**principal 优先、租户头兜底**：认证中间件验过 JWT 时，身份以 principal 为准
（``TrustLevel.JWT``）；没有 principal 时（内部调用 / 开发壳）以调用方给出的
actor 为准（``TrustLevel.INTERNAL`` —— 没有验签，调用方自己就是信任边界）。
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any
from uuid import UUID

from qzdap_agent_runtime.gateway.identity import (
    REASON_CREDENTIALS_MISSING,
    Identity,
    IdentityRejected,
    IdentityRequest,
)
from qzdap_agent_runtime.gateway.normalizer import (
    NormalizerContext,
    resolve_idempotency_key,
)
from qzdap_agent_runtime.gateway.types import (
    ActorContext,
    AuthMethod,
    ChannelType,
    InboundMessage,
    TrustLevel,
)

#: 租户 / 工作区 / 用户的请求头（大小写不敏感，调用方给的是小写键）。
HEADER_TENANT = "x-tenant-id"
HEADER_WORKSPACE = "x-workspace-id"
HEADER_USER = "x-user-id"


class WebIdentityVerifier:
    """② web 的身份 —— **principal 优先，租户头兜底**。

    ``IdentityRequest.actor_id`` / ``tenant_id`` / ``workspace_id`` / ``roles``
    由调用方（HTTP 层）填：能从 principal 填的优先从 principal 填。
    """

    async def verify(self, request: IdentityRequest) -> Identity:
        headers = {key.lower(): value for key, value in request.headers.items()}
        tenant_id = request.tenant_id or _uuid_or_none(headers.get(HEADER_TENANT))
        actor_id = request.actor_id or _uuid_or_none(headers.get(HEADER_USER))
        if tenant_id is None or actor_id is None:
            raise IdentityRejected(
                "web identity needs tenant_id and actor_id",
                reason_code=REASON_CREDENTIALS_MISSING,
                trace_id=request.trace_id,
            )
        workspace_id = request.workspace_id or _uuid_or_none(headers.get(HEADER_WORKSPACE))
        from_principal = request.actor_id is not None
        return Identity(
            actor=ActorContext(
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                actor_id=actor_id,
                roles=request.roles,
                actor_kind="user",
            ),
            trust=TrustLevel.JWT if from_principal else TrustLevel.INTERNAL,
            auth_method=AuthMethod.JWT if from_principal else AuthMethod.INTERNAL,
            auth_evidence=(f"principal:{actor_id}" if from_principal else f"headers:{actor_id}"),
        )


class WebChatNormalizer:
    """③ web 的归一化 —— 请求体 → 标准入站消息。

    请求体（``POST /api/sessions/{id}/turns/stream``）::

        {"content": "...", "clientRequestId": "...", "model": "...", "route_id": "..."}

    - **外部会话标识** = 路径里的 session_id（由 ① 放进 ``external_chat_id``）；
    - **幂等键**：客户端 ``clientRequestId``（strong）→ 没有则内容指纹（**weak**，
      只记录不抑制，决策 #5）。
    """

    channel_type = ChannelType.WEB

    def normalize(
        self,
        *,
        body: bytes,
        headers: Mapping[str, str],
        context: NormalizerContext,
    ) -> InboundMessage:
        _ = headers
        payload = _safe_json(body)
        text = str(payload.get("content") or payload.get("message") or "")
        client_request_id = str(payload.get("clientRequestId") or "")
        chat_id = context.external_chat_id or ""
        key = resolve_idempotency_key(
            client_request_id=client_request_id or None,
            channel=str(context.channel_type),
            chat_id=chat_id,
            user_id=str(context.actor.actor_id),
            text=text,
        )
        return InboundMessage(
            actor=context.actor,
            channel_type=context.channel_type,
            channel_id=context.channel_id,
            external_chat_id=chat_id,
            external_user_id=str(context.actor.actor_id),
            explicit_agent_id=None,
            idempotency=key,
            external_message_id=client_request_id or None,
            payload_hash=hashlib.sha256(body or b"").hexdigest(),
            trace_id=context.trace_id,
            text=text,
            # 幂等键强度不足（weak）→ 本轮禁用有副作用的工具（决策 #5）。
            unprotected=key.strength == "weak",
        )


def _uuid_or_none(value: str | None) -> UUID | None:
    if not value:
        return None
    try:
        return UUID(str(value))
    except ValueError:
        return None


def _safe_json(body: bytes) -> dict[str, Any]:
    if not body:
        return {}
    try:
        decoded = json.loads(body)
    except json.JSONDecodeError:
        return {}
    if not isinstance(decoded, dict):
        return {}
    return decoded


__all__ = [
    "HEADER_TENANT",
    "HEADER_USER",
    "HEADER_WORKSPACE",
    "WebChatNormalizer",
    "WebIdentityVerifier",
]
