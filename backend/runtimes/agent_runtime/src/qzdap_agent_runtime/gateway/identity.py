"""② Auth Identity —— 端口 + 三种实现（web JWT / IM HMAC / internal）。

依据：``docs/refactor/session-architecture/gateway-refactor-plan.md`` §2.2 / §3.2 /
§10 Stage 2。

**信任模型差异必须保留**（§3.2）：web 的 actor 是「已认证用户带租户头」，IM 的 actor
是「平台签名证明的机器身份」。两者都归一成 :class:`ActorContext`，但 ``trust`` /
``auth_method`` 不同 —— **IM 的服务账号不能当作用户权限使用**。

**这一层没有框架依赖**：验签用标准库 HMAC，JWT 委托 ``qzdap_auth``，错误用
``qzdap_kernel`` 的 AppError 体系。
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol
from uuid import UUID

from qzdap_kernel.errors import AuthenticationError

from qzdap_agent_runtime.gateway.types import (
    ActorContext,
    AuthMethod,
    TrustLevel,
)

# 时间戳容差（秒）—— 沿用旧路径 ``DEFAULT_TIMESTAMP_TOLERANCE_SECONDS``。
DEFAULT_TIMESTAMP_TOLERANCE_SECONDS = 300

# ── 拒绝原因码（稳定契约）────────────────────────────────────────────────
REASON_SIGNATURE_INVALID = "WEBHOOK_SIGNATURE_INVALID"
REASON_TIMESTAMP_SKEW = "WEBHOOK_TIMESTAMP_SKEW"
REASON_CREDENTIALS_MISSING = "IDENTITY_CREDENTIALS_MISSING"
REASON_TOKEN_INVALID = "TOKEN_INVALID"
REASON_SERVICE_ACCOUNT_MISSING = "SERVICE_ACCOUNT_NOT_CONFIGURED"


class IdentityRejected(AuthenticationError):
    """鉴权失败 —— 带稳定的 reason code 与 trace_id。

    **trace_id 必须带上**：鉴权失败是最需要被追踪的一类请求，而它往往在
    「还没进入业务处理」时就结束了（§2.3 的顺序规则 ②）。
    """

    code = "IDENTITY_REJECTED"
    status = 401

    def __init__(
        self, message: str = "", *, reason_code: str, trace_id: str = ""
    ) -> None:
        super().__init__(
            message or reason_code,
            code=reason_code,
            details={"trace_id": trace_id} if trace_id else None,
        )
        self.reason_code = reason_code
        self.trace_id = trace_id


@dataclass(frozen=True, slots=True)
class ServiceAccount:
    """渠道登记的服务账号 —— IM 的 actor 由此物化。

    **它不是用户**：它代表「这个渠道以谁的身份说话」，不能当作用户权限使用
    （§3.2）。``user_id`` 是会话的归属者，``agent_id`` 是应答消息的智能体。
    """

    user_id: UUID
    agent_id: UUID
    agent_version: str = ""
    roles: tuple[str, ...] = ()

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any] | None) -> ServiceAccount | None:
        """从渠道配置解析服务账号 —— **配置缺失或不合法返回 None**，不抛异常。

        「配置错了」不是「请求有问题」—— 调用方据此拒绝**渠道**，而不是拒绝
        这一次请求。
        """
        if not raw:
            return None
        try:
            user_id = UUID(str(raw["user_id"]))
            agent_id = UUID(str(raw["agent_id"]))
        except (KeyError, TypeError, ValueError):
            return None
        return cls(
            user_id=user_id,
            agent_id=agent_id,
            agent_version=str(raw.get("agent_version") or ""),
            roles=tuple(str(item) for item in (raw.get("roles") or ())),
        )

    def to_mapping(self) -> dict[str, Any]:
        return {
            "user_id": str(self.user_id),
            "agent_id": str(self.agent_id),
            "agent_version": self.agent_version,
            "roles": list(self.roles),
        }


@dataclass(frozen=True, slots=True)
class IdentityRequest:
    """② 的输入 —— 传输层（①）带来的原始材料。"""

    trace_id: str
    headers: Mapping[str, str] = field(default_factory=dict)
    body: bytes = b""
    secret: bytes = b""
    tolerance_seconds: int = DEFAULT_TIMESTAMP_TOLERANCE_SECONDS
    tenant_id: UUID | None = None
    workspace_id: UUID | None = None
    actor_id: UUID | None = None
    service_account: ServiceAccount | None = None
    roles: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Identity:
    """② 的判定结果 —— 归一后的身份 + 信任级别。

    ``actor`` **可以是 None**：验签成功但渠道没登记服务账号时，请求是可信的，
    却还没有「以谁的身份说话」的答案 —— 那是**渠道配置问题**，不是**请求问题**
    （§3.2：IM 的 actor 由渠道配置物化）。
    """

    actor: ActorContext | None
    trust: TrustLevel
    auth_method: AuthMethod
    auth_evidence: str


class IdentityVerifier(Protocol):
    """② Auth Identity 的端口。"""

    async def verify(self, request: IdentityRequest) -> Identity:
        """判定请求的身份。

        失败时抛 :class:`IdentityRejected`（带 reason code 与 trace_id）。
        """
        ...


class HmacWebhookVerifier:
    """IM 渠道的验签 —— HMAC(secret, ``f"{ts}." + body``) + 时间戳容差。

    ⚠️ **验签必须针对原始字节**，且要在解析之前（§2.3 的顺序规则 ①）：
    未验签的 payload 不能进解析器。
    """

    def __init__(self, *, clock: Any = None) -> None:
        self._clock = clock

    def _now(self) -> int:
        if self._clock is not None:
            return int(self._clock.now().timestamp())
        import time

        return int(time.time())

    async def verify(self, request: IdentityRequest) -> Identity:
        headers = {k.lower(): v for k, v in request.headers.items()}
        ts_raw = headers.get("x-webhook-timestamp")
        sig_raw = headers.get("x-webhook-signature")
        if not ts_raw or not sig_raw:
            raise IdentityRejected(
                "missing X-Webhook-Timestamp / X-Webhook-Signature",
                reason_code=REASON_SIGNATURE_INVALID,
                trace_id=request.trace_id,
            )
        try:
            ts = int(ts_raw)
        except ValueError as exc:
            raise IdentityRejected(
                "X-Webhook-Timestamp must be an integer",
                reason_code=REASON_SIGNATURE_INVALID,
                trace_id=request.trace_id,
            ) from exc

        if abs(self._now() - ts) > request.tolerance_seconds:
            raise IdentityRejected(
                f"webhook timestamp {ts} outside ±{request.tolerance_seconds}s",
                reason_code=REASON_TIMESTAMP_SKEW,
                trace_id=request.trace_id,
            )

        if request.secret:
            expected = hmac.new(
                request.secret,
                f"{ts}.".encode() + request.body,
                hashlib.sha256,
            ).hexdigest()
            provided = sig_raw.split("=", 1)[-1] if "=" in sig_raw else sig_raw
            if not hmac.compare_digest(expected, provided):
                raise IdentityRejected(
                    "webhook signature does not match",
                    reason_code=REASON_SIGNATURE_INVALID,
                    trace_id=request.trace_id,
                )

        account = request.service_account
        actor = (
            ActorContext(
                tenant_id=request.tenant_id,
                workspace_id=request.workspace_id,
                actor_id=account.user_id,
                roles=account.roles,
                actor_kind="service_account",
            )
            if account is not None
            else None
        )
        return Identity(
            actor=actor,
            trust=TrustLevel.VERIFIED_HMAC,
            auth_method=AuthMethod.CHANNEL_SIGNATURE,
            auth_evidence=f"hmac:ts={ts}",
        )


class JwtIdentityVerifier:
    """web 的 JWT —— 委托 ``qzdap_auth`` 的 ``JWTVerifier`` 验签并解析 claims。"""

    def __init__(self, verifier: Any) -> None:
        self._verifier = verifier

    async def verify(self, request: IdentityRequest) -> Identity:
        headers = {k.lower(): v for k, v in request.headers.items()}
        raw = headers.get("authorization") or ""
        if not raw.lower().startswith("bearer "):
            raise IdentityRejected(
                "missing bearer token",
                reason_code=REASON_CREDENTIALS_MISSING,
                trace_id=request.trace_id,
            )
        token = raw.split(" ", 1)[1].strip()
        try:
            claims = await asyncio.to_thread(self._verifier.verify, token)
        except AuthenticationError as exc:
            raise IdentityRejected(
                str(exc),
                reason_code=REASON_TOKEN_INVALID,
                trace_id=request.trace_id,
            ) from exc
        try:
            actor_id = UUID(str(claims["sub"]))
            tenant_id = UUID(str(claims["tid"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise IdentityRejected(
                "token is missing sub/tid claims",
                reason_code=REASON_TOKEN_INVALID,
                trace_id=request.trace_id,
            ) from exc
        workspace_raw = claims.get("wid")
        workspace_id = UUID(str(workspace_raw)) if workspace_raw else None
        roles = tuple(str(item) for item in (claims.get("roles") or ()))
        actor = ActorContext(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            actor_id=actor_id,
            roles=roles or request.roles,
            actor_kind="user",
        )
        return Identity(
            actor=actor,
            trust=TrustLevel.JWT,
            auth_method=AuthMethod.JWT,
            auth_evidence=f"jwt:{actor_id}",
        )


class InternalIdentityVerifier:
    """内部调用 —— 信任级别 INTERNAL。

    内部调用没有签名也没有 token：调用方**自己**就是信任边界。因此 actor 必须
    由调用方显式给出（``request.actor_id``），不给就没有身份。
    """

    async def verify(self, request: IdentityRequest) -> Identity:
        if request.actor_id is None or request.tenant_id is None:
            raise IdentityRejected(
                "internal call must state actor_id and tenant_id",
                reason_code=REASON_CREDENTIALS_MISSING,
                trace_id=request.trace_id,
            )
        account = request.service_account
        actor = ActorContext(
            tenant_id=request.tenant_id,
            workspace_id=request.workspace_id,
            actor_id=request.actor_id,
            roles=account.roles if account is not None else request.roles,
            actor_kind="service_account" if account is not None else "user",
        )
        return Identity(
            actor=actor,
            trust=TrustLevel.INTERNAL,
            auth_method=AuthMethod.INTERNAL,
            auth_evidence=f"internal:{request.actor_id}",
        )


__all__ = [
    "DEFAULT_TIMESTAMP_TOLERANCE_SECONDS",
    "REASON_CREDENTIALS_MISSING",
    "REASON_SERVICE_ACCOUNT_MISSING",
    "REASON_SIGNATURE_INVALID",
    "REASON_TIMESTAMP_SKEW",
    "REASON_TOKEN_INVALID",
    "HmacWebhookVerifier",
    "Identity",
    "IdentityRejected",
    "IdentityRequest",
    "IdentityVerifier",
    "InternalIdentityVerifier",
    "JwtIdentityVerifier",
    "ServiceAccount",
]
