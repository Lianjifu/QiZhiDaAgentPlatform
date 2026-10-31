"""Gateway 门面 —— ①→②→③ 的编排，④ 的三个动作。

依据：``docs/refactor/session-architecture/gateway-refactor-plan.md`` §2.3
（三条必须写死的顺序规则）、§9.1（``facade.py``）、§10 Stage 4a。

**编排顺序不可换**：

```
① 查渠道（拿密钥 / 租户 / 工作区）→ ② 验签取身份 → ③ 归一化（算幂等键）→ ④ claim
```

- ① **在 ② 之前**：验签必须针对**原始字节**，而密钥挂在渠道配置上 → 先知道用哪把
  密钥，才能验签；也让「鉴权失败的请求」也带得上 trace（顺序规则 ②）。
- ③ **在 ④ 之前**：幂等键的**原料**在 ③ 采集（客户端 id / 平台消息 id / 内容指纹），
  ④ 负责**落库与短路**（顺序规则 ③）。

⚠️ **④ 的 claim 由「即将开始轮次的一方」发起**（§10 Stage 4a 的实施修正）：

- **web（同步）**：请求方 ``accept`` → ``claim`` → 跑轮次 → ``complete``；
- **IM（异步）**：门口 ``accept``（①②③）→ 发到总线 → **消费方** ``claim`` →
  跑轮次 → ``complete``。

理由：**只有开始轮次的一方知道「这一轮跑没跑起来」** —— 失败时要把键
``release`` 掉（否则调用方重试会被误判成重复，键就白烧了）。IM 的门口不知道
轮次成败，所以 claim 不能只发生在门口。

**这一层没有框架依赖**：渠道查询走端口（实现在渠道模块侧），验签走
:class:`IdentityVerifier`，归一化走 :class:`MessageNormalizer`，幂等走
:class:`IdempotencyGuard` —— Gateway 只持端口，不碰 DB、不碰框架。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

from qzdap_agent_runtime.gateway.idempotency import (
    SENTINEL_WORKSPACE_ID,
    IdempotencyGuard,
    InboxScope,
)
from qzdap_agent_runtime.gateway.identity import (
    REASON_SERVICE_ACCOUNT_MISSING,
    Identity,
    IdentityRejected,
    IdentityRequest,
    IdentityVerifier,
    ServiceAccount,
)
from qzdap_agent_runtime.gateway.normalizer import (
    MessageNormalizer,
    NormalizerContext,
)
from qzdap_agent_runtime.gateway.replay import EventStore, ReplayResult
from qzdap_kernel.error_codes import ErrorCode

if TYPE_CHECKING:
    from collections.abc import Mapping
    from uuid import UUID

    from qzdap_agent_runtime.gateway.types import (
        ChannelCapabilities,
        ChannelType,
        IdempotencyDecision,
        InboundMessage,
        RawIngress,
    )


class GatewayChannelNotFound(Exception):
    """① 查不到渠道 —— 入口地址本身就不对（不是请求内容的问题）。"""

    def __init__(self, channel_id: UUID) -> None:
        super().__init__(f"channel {channel_id} not found")
        self.channel_id = channel_id
        self.code = ErrorCode.CHANNEL_NOT_FOUND.value


class GatewayNormalizerMissing(Exception):
    """③ 没有该渠道的归一化器 —— 装配漏了（不是请求的问题）。"""

    def __init__(self, channel_type: ChannelType) -> None:
        super().__init__(f"no normalizer registered for channel type {channel_type}")
        self.channel_type = channel_type
        self.code = ErrorCode.INBOUND_ADAPTER_MISSING.value


@dataclass(frozen=True, slots=True)
class ChannelDescriptor:
    """① 的产物 —— 渠道的**鉴权材料与归属**。

    ⚠️ 这是**裁剪过的**渠道视图：只带验签与身份需要的东西，不带渠道实体本身
    （那是渠道模块的领域对象，Gateway 不持有它）。
    """

    channel_id: UUID
    channel_type: ChannelType
    tenant_id: UUID
    workspace_id: UUID | None = None
    secret: bytes = b""
    service_account: ServiceAccount | None = None


class ChannelDirectoryPort(Protocol):
    """① 的端口 —— 渠道目录查询。

    **实现在渠道模块侧**（它有渠道实体与密文仓储）—— Gateway 只持端口，
    不反向依赖渠道模块（§9.2.1 的依赖方向）。
    """

    async def get(self, channel_id: UUID) -> ChannelDescriptor | None: ...


@dataclass(frozen=True, slots=True)
class AcceptedIngress:
    """①②③ 的产物 —— 标准入站消息 + 身份。

    **还没有 claim**（④）：claim 由即将开始轮次的一方发起（见模块说明）。
    """

    message: InboundMessage
    identity: Identity


def scope_for(message: InboundMessage) -> InboxScope:
    """由标准入站消息推导幂等作用域 —— (tenant, workspace, channel)。

    - **IM**：``channel_id`` 是**渠道行 id**（不同渠道的消息互不抑制）；
    - **web / api**：没有渠道行，用渠道类型（``'web'`` / ``'api'``）——
      与 :meth:`InboxScope.for_web` 的合成值约定一致（§3.1）。

    ⚠️ **workspace 缺省时用哨兵 UUID**，不能改成 nullable —— 幂等索引的列是
    NOT NULL，NULL 互不相等会让幂等失效。
    """
    return InboxScope(
        tenant_id=message.actor.tenant_id,
        workspace_id=message.actor.workspace_id or SENTINEL_WORKSPACE_ID,
        channel_id=(str(message.channel_id) if message.channel_id else str(message.channel_type)),
    )


class Gateway:
    """Gateway 门面 —— 入站四段流水线 + 幂等守卫的三个动作。"""

    def __init__(
        self,
        *,
        identity: IdentityVerifier,
        normalizers: Mapping[ChannelType, MessageNormalizer],
        idempotency: IdempotencyGuard,
        channels: ChannelDirectoryPort | None = None,
        capabilities: Any = None,
        tolerance_seconds: int = 300,
        events: EventStore | None = None,
    ) -> None:
        self._identity = identity
        self._normalizers = dict(normalizers)
        self._idempotency = idempotency
        self._channels = channels
        self._capabilities = capabilities
        self._tolerance = tolerance_seconds
        self._events = events

    # ── ①②③ ───────────────────────────────────────────────────────────

    async def accept(
        self,
        raw: RawIngress,
        *,
        tolerance_seconds: int | None = None,
        actor_id: UUID | None = None,
        roles: tuple[str, ...] = (),
    ) -> AcceptedIngress:
        """受理一条入站 —— ① 查渠道 → ② 验签 → ③ 归一化。

        **不落库、不短路**（那是 ④ 的 :meth:`claim`）—— 因为**开始轮次的一方**
        才可能需要 ``release`` 这把键（见模块说明）。
        """
        descriptor = await self._resolve_channel(raw)
        channel_type = descriptor.channel_type if descriptor else raw.channel_type
        capabilities = self._capabilities_for(channel_type)

        identity = await self._identity.verify(
            IdentityRequest(
                trace_id=raw.trace_id,
                headers=raw.headers,
                body=raw.body,
                secret=descriptor.secret if descriptor else b"",
                tolerance_seconds=(
                    tolerance_seconds if tolerance_seconds is not None else self._tolerance
                ),
                tenant_id=descriptor.tenant_id if descriptor else None,
                workspace_id=descriptor.workspace_id if descriptor else None,
                actor_id=actor_id,
                service_account=descriptor.service_account if descriptor else None,
                roles=roles,
            )
        )
        if identity.actor is None:
            # 验签通过但**没有身份** —— 渠道没登记服务账号（配置问题）。
            # 交给调用方决定「拒渠道」还是「拒请求」。
            raise IdentityRejected(
                "channel has no service account registered",
                reason_code=REASON_SERVICE_ACCOUNT_MISSING,
                trace_id=raw.trace_id,
            )

        normalizer = self._normalizers.get(channel_type)
        if normalizer is None:
            raise GatewayNormalizerMissing(channel_type)

        message = normalizer.normalize(
            body=raw.body,
            headers=raw.headers,
            context=NormalizerContext(
                actor=identity.actor,
                channel_type=channel_type,
                channel_id=raw.channel_id,
                trace_id=raw.trace_id,
                # 外部会话标识（web 的 session_id）—— IM 的聊天 id 在协议载荷里。
                external_chat_id=raw.ingress_ref,
                capabilities=capabilities,
            ),
        )
        return AcceptedIngress(message=message, identity=identity)

    # ── ④ ─────────────────────────────────────────────────────────────

    async def claim(self, message: InboundMessage) -> IdempotencyDecision:
        """④ 的原子 claim —— **先 claim 再起轮次**。

        命中 strong 键 → ``duplicate`` / ``in_progress`` → **不得**再跑一轮。
        """
        return await self._idempotency.accept(
            scope_for(message),
            message.idempotency,
            payload_hash=message.payload_hash,
            external_message_id=message.external_message_id,
            trace_id=message.trace_id,
        )

    async def complete(self, decision: IdempotencyDecision, *, turn_id: UUID | None = None) -> None:
        """这一轮跑完了 —— 键被消费。"""
        await self._idempotency.complete(decision, turn_id=turn_id)

    async def release(self, decision: IdempotencyDecision) -> None:
        """这一轮**根本没跑起来** —— 键不该被消费，调用方还能用同一个键重试。"""
        await self._idempotency.release(decision)

    # ── 重放（Stage 4b）────────────────────────────────────────────────

    async def replay(self, turn_id: UUID, *, tenant_id: UUID, after_seq: int = 0) -> ReplayResult:
        """重放上一轮的事件流 —— **重复请求的正确行为**（§4.5）。

        ``after_seq`` 是客户端带回来的 ``Last-Event-ID``：只重放它**之后**的
        事件（断线续传的位置）。

        没有装配事件存储（``events is None``）→ 返回空结果 —— 调用方据此
        降级（「重复请求不是错误，但也没有可重放的流」）。
        """
        if self._events is None:
            return ReplayResult(turn_id=turn_id, status=None, events=[])
        events = await self._events.get_events(turn_id, tenant_id=tenant_id, after_seq=after_seq)
        status = await self._events.get_turn_status(turn_id, tenant_id=tenant_id)
        return ReplayResult(turn_id=turn_id, status=status, events=events)

    # ── helpers ────────────────────────────────────────────────────────

    async def _resolve_channel(self, raw: RawIngress) -> ChannelDescriptor | None:
        """① 查渠道 —— **在 ② 之前**（顺序规则 ①）。

        没有渠道行的入口（web / api）→ 返回 None：这类入口不按渠道配置验签。
        """
        if raw.channel_id is None or self._channels is None:
            return None
        descriptor = await self._channels.get(raw.channel_id)
        if descriptor is None:
            raise GatewayChannelNotFound(raw.channel_id)
        return descriptor

    def _capabilities_for(self, channel_type: ChannelType) -> ChannelCapabilities:
        if self._capabilities is not None:
            return self._capabilities(channel_type)
        from qzdap_agent_runtime.gateway.channels import capabilities_for

        return capabilities_for(channel_type)


__all__ = [
    "AcceptedIngress",
    "ChannelDescriptor",
    "ChannelDirectoryPort",
    "Gateway",
    "GatewayChannelNotFound",
    "GatewayNormalizerMissing",
    "scope_for",
]
