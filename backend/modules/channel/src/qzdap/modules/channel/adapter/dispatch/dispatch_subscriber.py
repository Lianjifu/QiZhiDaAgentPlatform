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

⚠️ **已弃用（Gateway 方案 §10 Stage 4a，台账 G9）** —— 渠道入站应当**直接**
进 ``Gateway.accept``，不再经过「总线 → 订阅者 → 临时会话」这一跳。
**本文件是本层的删除对象**（Stage 5），但**必须与「切 IM 入口」+ Session
Stage 5b（删 ``use_cases/*``）同一个 PR** —— 否则 IM 断。
本轮已把它改成「消费标准入站消息 + 走 ④ 的 claim + 走出站 sink」，
**旧路径仍在服役**（``record_legacy_call("G9")`` 就是这个事实的观测）。

⚠️ **``unprotected`` 目前只记录不生效** —— 决策 #5 的兑现点（剔除副作用工具）在
Agent Loop / Execution（Gateway 方案 §0.5 的前置依赖）。IM 的三个平台都带消息 id
→ **strong 键** → 实际暴露面只有「注册成渠道的 web / api 且没给消息 id」。
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from qzdap_agent_runtime.gateway.channels import capabilities_for
from qzdap_agent_runtime.gateway.identity import ServiceAccount
from qzdap_agent_runtime.gateway.outbound import OutboundTarget, ResultSink
from qzdap_agent_runtime.gateway.types import InboundMessage
from qzdap_agent_runtime.result.events import MessageEvent
from qzdap_observability.metrics import record_legacy_call

if TYPE_CHECKING:
    from uuid import UUID

    from qzdap.modules.channel.application.ports import ChannelRepository
    from qzdap_agent_runtime.gateway.facade import Gateway

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
        sink: ResultSink,
        clock: Any,
        open_session: Any,
        gateway: Gateway,
        model: str = DEFAULT_MODEL,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self._channels = channel_repository
        self._ar_factory = agent_runtime_factory
        self._sink = sink
        self._clock = clock
        self._open_session = open_session
        self._gateway = gateway
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
        # ⚠️ **claim 在消费方发起**（不是门口）：只有开始轮次的一方知道这一轮
        # 跑没跑起来，失败时才能 release 掉这把键（§10 Stage 4a）。
        decision = await self._gateway.claim(message)
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
            await self._gateway.release(decision)
            _log.exception(
                "channel dispatch turn failed",
                extra={
                    "tenant_id": str(tenant_id),
                    "channel_id": str(channel_id),
                },
            )
            return

        await self._gateway.complete(decision, turn_id=turn_id)

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
        """出站 —— **走统一编码 + 投递**（Gateway ① 的出站，§6）。

        旧的实现是「按 channel_type 找适配器 → 直接发纯文本」；现在消息先变成
        标准结果事件，再由编码器按**渠道能力**决定怎么表达（卡片 / 降级文本），
        投递结果（含降级留痕）由 sink 记账。
        """
        metadata: dict[str, str] = {"channel_id": str(message.channel_id)}
        if turn_id is not None:
            metadata["turn_id"] = str(turn_id)
        event = MessageEvent(
            turn_id=str(turn_id or message.trace_id or "im-turn"),
            seq=0,
            event_id=str(uuid4()),
            trace_id=message.trace_id or None,
            delta=text,
        )
        outcome = await self._sink.deliver(
            event,
            target=OutboundTarget(
                channel_type=channel_type,
                external_chat_id=message.external_chat_id,
                capabilities=capabilities_for(channel_type),
                metadata=metadata,
            ),
        )
        if not outcome.ok:
            _log.warning(
                "im reply not delivered: status=%s error=%s",
                outcome.status,
                outcome.error,
                extra={"channel_id": str(message.channel_id)},
            )


__all__ = ["INBOUND_MESSAGE_EVENT", "ChannelDispatchSubscriber"]
