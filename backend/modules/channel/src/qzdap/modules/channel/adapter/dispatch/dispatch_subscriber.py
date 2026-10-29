"""Channel → agent_runtime dispatch subscriber.

Subscribes to the standard inbound message (:class:`InboundMessage`) on the
event bus, opens an ephemeral session **owned by the channel's registered
service account**, runs a single agent turn through
:class:`RunTurnCompletionUseCase`, and writes the final assistant message
back through the outbound adapter registered for the channel's
``channel_type``.

⚠️ **总线按类名路由**（``EventEnvelope.event_name`` = 类名），因此这里订阅的是
``"InboundMessage"`` —— **不是** dotted 的 topic 串。旧实现按 ``TOPIC`` 订阅，
而发布方用的是类名 → **这条链路从未被触发过**（§10 Stage 3 / 附录 C.2）。

* idempotency: **session_inbox 的原子 claim**（Gateway ④）—— 取代了旧的进程内
  LRU：LRU 跨不了进程、也没有过期概念，且键空间只增不减。
* workspace resolution: looked up via :class:`ChannelRepository`
  (``get_by_id``), since the inbound message carries the channel id.
* failures: logged and swallowed; never re-raised (the bus logs
  handler exceptions but we still log a domain-level summary here).

⚠️ **``unprotected`` 目前只记录不生效** —— 决策 #5 的兑现点（剔除副作用工具）在
Agent Loop / Execution（Gateway 方案 §0.5 的前置依赖）。IM 的三个平台都带消息 id
→ **strong 键** → 实际暴露面只有「注册成渠道的 web / api 且没给消息 id」。
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from qzdap_agent_runtime.gateway.idempotency import (
    SENTINEL_WORKSPACE_ID,
    IdempotencyGuard,
    InboxScope,
)
from qzdap_agent_runtime.gateway.identity import ServiceAccount
from qzdap_agent_runtime.gateway.types import InboundMessage
from qzdap_observability.metrics import record_legacy_call

if TYPE_CHECKING:
    from uuid import UUID

    from qzdap.modules.channel.application.ports import (
        ChannelRepository,
        OutboundAdapter,
    )

_log = logging.getLogger("qzdap.channel.dispatch")

# ⚠️ **服务账号不再是全局常量** —— IM 的 actor 由**渠道登记的服务账号**物化
# （Gateway 方案 §3.2 / §10 Stage 2，台账 G3）。所有租户、所有渠道共用一个
# 硬编码身份，意味着「渠道 A 的消息记在渠道 B 名下」这类问题无处追查。
#
# 渠道没登记服务账号 → **不跑这一轮**（配置问题，不是请求问题），并留下错误日志。

DEFAULT_MODEL = "default"
DEFAULT_TIMEOUT_SECONDS = 60

#: 总线的订阅键 = 事件类名（``EventEnvelope.event_name``）。
INBOUND_MESSAGE_EVENT = InboundMessage.__name__


class ChannelDispatchSubscriber:
    """Wires the standard inbound message → ``RunTurnCompletionUseCase``."""

    def __init__(
        self,
        *,
        channel_repository: ChannelRepository,
        agent_runtime_factory: Any,
        outbound_registry_getter: Any,
        clock: Any,
        open_session: Any,
        idempotency: IdempotencyGuard,
        model: str = DEFAULT_MODEL,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self._channels = channel_repository
        self._ar_factory = agent_runtime_factory
        self._outbound_getter = outbound_registry_getter
        self._clock = clock
        self._open_session = open_session
        self._idempotency = idempotency
        self._model = model
        self._timeout = timeout_seconds

    async def install(self, event_bus: Any) -> None:
        """Subscribe to the inbound message event.

        ⚠️ **键是事件类名**（总线按类名路由）—— 不是 dotted 的 topic 串。
        """
        await event_bus.subscribe(INBOUND_MESSAGE_EVENT, self._handle_envelope)
        _log.info(
            "channel dispatch subscriber installed",
            extra={"event_name": INBOUND_MESSAGE_EVENT},
        )

    # ── handler ─────────────────────────────────────────────────────────

    async def _handle_envelope(self, envelope: Any) -> None:
        """Bus-level entrypoint; payload is dict from ``EventEnvelope``."""
        if isinstance(envelope, dict):
            payload = envelope.get("payload", envelope)
        else:
            payload = getattr(envelope, "payload", None) or {}
        if not isinstance(payload, dict):
            _log.warning("envelope payload is not a dict: %r", payload)
            return
        try:
            message = InboundMessage.from_payload(payload)
        except (KeyError, ValueError, TypeError):
            _log.exception("invalid inbound message payload: %r", payload)
            return
        await self._handle_event(message)

    async def _handle_event(self, message: InboundMessage) -> None:
        """Domain-level dispatch."""
        record_legacy_call("G9")  # dispatch_subscriber.py 整体
        channel_id = message.channel_id
        tenant_id = message.actor.tenant_id

        if channel_id is None:
            _log.warning("inbound message has no channel id; dropping")
            return

        # Resolve the channel row — it carries the workspace and the
        # answering agent (via the registered service account).
        channel = await self._channels.get_by_id(channel_id)
        if channel is None:
            _log.warning(
                "channel not found; dropping event",
                extra={
                    "channel_id": str(channel_id),
                    "tenant_id": str(tenant_id),
                },
            )
            return

        # 物化 IM 的 actor —— 渠道登记的服务账号（不是全局常量）。
        account = ServiceAccount.from_mapping(getattr(channel, "service_account", None))
        if account is None:
            _log.error(
                "channel has no service account registered; dropping event",
                extra={
                    "channel_id": str(channel_id),
                    "tenant_id": str(tenant_id),
                },
            )
            return

        # ④ Idempotency Guard：**先 claim 再起轮次** —— 同一平台消息投递两次
        # 只能起一轮。旧的进程内 LRU 已被这一步取代（跨进程可见 + 有过期）。
        decision = await self._idempotency.accept(
            InboxScope(
                tenant_id=tenant_id,
                workspace_id=(
                    channel.workspace_id
                    or message.actor.workspace_id
                    or SENTINEL_WORKSPACE_ID
                ),
                channel_id=str(channel_id),
            ),
            message.idempotency,
            payload_hash=message.payload_hash,
            external_message_id=message.external_message_id,
            trace_id=message.trace_id,
        )
        if decision.is_duplicate:
            _log.info(
                "channel dispatch duplicate; skipping turn",
                extra={
                    "tenant_id": str(tenant_id),
                    "channel_id": str(channel_id),
                    "outcome": decision.outcome,
                },
            )
            return

        # Open an ephemeral agent_runtime session, create + run a turn,
        # then write the reply via the outbound adapter (best effort).
        try:
            _, final_message, turn_id = await self._run_turn(message, channel, account)
        except Exception:
            # 这一轮**根本没跑起来** → 键不该被消费（④ 的 release），
            # 否则平台重投时会被判成重复而永远丢掉。
            await self._idempotency.release(decision)
            _log.exception(
                "channel dispatch turn failed",
                extra={
                    "tenant_id": str(tenant_id),
                    "channel_id": str(channel_id),
                },
            )
            return

        await self._idempotency.complete(decision, turn_id=turn_id)

        if not final_message:
            return

        await self._send_reply(
            message=message,
            channel_type=getattr(channel, "type", message.channel_type),
            text=final_message[:4096],
            turn_id=turn_id,
        )

    # ── helpers ──────────────────────────────────────────────────────────

    async def _run_turn(
        self, message: InboundMessage, channel: Any, account: ServiceAccount
    ) -> tuple[UUID, str, UUID | None]:
        """Open session, create agent turn, drain to completion."""
        from qzdap_schema.ids import AgentId, UserId

        tenant_id = message.actor.tenant_id
        workspace_id = channel.workspace_id
        chat_id = message.external_chat_id
        channel_type = str(message.channel_type)

        async def _drive() -> tuple[UUID, str, UUID | None]:
            session_obj = self._open_session()
            async with session_obj as sess:
                svc = self._ar_factory.for_session(sess)
                record_legacy_call("R1")  # IM 每条消息新建临时 session
                session = await svc.create_session().execute(
                    tenant_id=tenant_id,
                    workspace_id=workspace_id,
                    owner_id=UserId(account.user_id),
                    agent_id=AgentId(account.agent_id),
                    agent_version=account.agent_version,
                    metadata={
                        "channel_id": str(message.channel_id),
                        "channel_type": channel_type,
                        "external_chat_id": chat_id,
                    },
                )
                user_input = f"[channel={channel_type} chat={chat_id}] {message.text}"
                record_legacy_call("X2")  # 第二套 turn 实现
                result = await svc.run_turn_to_completion().execute(
                    tenant_id=tenant_id,
                    workspace_id=workspace_id,
                    owner_id=UserId(account.user_id),
                    session_id=session.id,
                    user_input=user_input,
                    model=self._model,
                )
                return (
                    session.id,
                    result.final_message or "",
                    result.turn_id,
                )

        return await asyncio.wait_for(_drive(), timeout=self._timeout)

    async def _send_reply(
        self,
        *,
        message: InboundMessage,
        channel_type: Any,
        text: str,
        turn_id: UUID | None,
    ) -> None:
        registry = self._outbound_getter()
        if registry is None:
            return
        # Outbound adapters are keyed by ChannelType. Match by string
        # value so the subscriber stays decoupled from the ChannelType
        # definition site.
        adapter: OutboundAdapter | None = None
        for key, candidate in registry.items():
            if str(key) == str(channel_type) or (
                getattr(key, "value", None) == channel_type
            ):
                adapter = candidate
                break
        if adapter is None:
            _log.info(
                "no outbound adapter for channel_type=%s; reply dropped",
                channel_type,
                extra={
                    "channel_id": str(message.channel_id),
                    "tenant_id": str(message.actor.tenant_id),
                },
            )
            return
        try:
            metadata: dict[str, str] = {
                "channel_id": str(message.channel_id),
            }
            if turn_id is not None:
                metadata["turn_id"] = str(turn_id)
            await adapter.send_reply(
                external_chat_id=message.external_chat_id,
                text=text,
                metadata=metadata,
            )
        except Exception:  # pragma: no cover - defensive
            _log.exception(
                "outbound send_reply failed",
                extra={"channel_id": str(message.channel_id)},
            )


__all__ = ["INBOUND_MESSAGE_EVENT", "ChannelDispatchSubscriber"]
