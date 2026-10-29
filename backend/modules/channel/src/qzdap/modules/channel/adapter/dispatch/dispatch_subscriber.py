"""Channel → agent_runtime dispatch subscriber.

Subscribes to :class:`ChannelMessageReceived` events on the in-process
event bus, opens an ephemeral session **owned by the channel's registered
service account**, runs a single agent turn through
:class:`RunTurnCompletionUseCase`, and writes the final assistant message
back through the outbound adapter registered for the channel's
``channel_type``.

v1 (P7-8):
* idempotency: process-local LRU keyed by
  ``(tenant_id, channel_id, message_key)`` — same message arriving
  twice in the dedup window does not start a second turn.
* workspace resolution: looked up via :class:`ChannelRepository`
  (``get_by_id``), since the inbound event payload only carries
  ``tenant_id`` + ``channel_id``.
* failures: logged and swallowed; never re-raised (the bus logs
  handler exceptions but we still log a domain-level summary here).
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from collections import OrderedDict
from typing import TYPE_CHECKING, Any
from uuid import UUID

from qzdap_agent_runtime.gateway.identity import ServiceAccount
from qzdap.modules.channel.domain.events import ChannelMessageReceived
from qzdap_observability.metrics import record_legacy_call

if TYPE_CHECKING:
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
DEDUP_WINDOW = 1024


class ChannelDispatchSubscriber:
    """Wires ``ChannelMessageReceived`` → ``RunTurnCompletionUseCase``."""

    def __init__(
        self,
        *,
        channel_repository: ChannelRepository,
        agent_runtime_factory: Any,
        outbound_registry_getter: Any,
        clock: Any,
        open_session: Any,
        model: str = DEFAULT_MODEL,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
        dedup_window: int = DEDUP_WINDOW,
    ) -> None:
        self._channels = channel_repository
        self._ar_factory = agent_runtime_factory
        self._outbound_getter = outbound_registry_getter
        self._clock = clock
        self._open_session = open_session
        self._model = model
        self._timeout = timeout_seconds
        # OrderedDict acts as a tiny LRU: re-insert on touch, evict from
        # the front when we exceed ``dedup_window``.
        self._seen: OrderedDict[tuple[UUID, UUID, str], None] = OrderedDict()
        self._dedup_window = dedup_window

    async def install(self, event_bus: Any) -> None:
        """Subscribe to :attr:`ChannelMessageReceived.TOPIC`."""
        await event_bus.subscribe(ChannelMessageReceived.TOPIC, self._handle_envelope)
        _log.info(
            "channel dispatch subscriber installed",
            extra={"topic": ChannelMessageReceived.TOPIC},
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
            evt = ChannelMessageReceived(
                channel_id=UUID(str(payload["channel_id"])),
                channel_type=str(payload["channel_type"]),
                external_user_id=str(payload["external_user_id"]),
                external_chat_id=str(payload["external_chat_id"]),
                text_preview=str(payload["text_preview"]),
                tenant_id=UUID(str(payload["tenant_id"])),
            )
        except (KeyError, ValueError, TypeError):
            _log.exception("invalid ChannelMessageReceived payload: %r", payload)
            return
        await self._handle_event(evt)

    async def _handle_event(self, evt: ChannelMessageReceived) -> None:
        record_legacy_call("G9")  # dispatch_subscriber.py 整体
        """Domain-level dispatch."""
        record_legacy_call("G6")  # IM 进程内 LRU 去重
        msg_key = self._message_key(evt)
        dedup_key = (evt.tenant_id, evt.channel_id, msg_key)
        if dedup_key in self._seen:
            _log.info(
                "channel dispatch dedup hit; skipping turn",
                extra={
                    "tenant_id": str(evt.tenant_id),
                    "channel_id": str(evt.channel_id),
                },
            )
            return
        self._seen[dedup_key] = None
        self._evict_dedup()

        # Resolve workspace via channel row.
        channel = await self._channels.get_by_id(evt.channel_id)
        if channel is None:
            _log.warning(
                "channel not found; dropping event",
                extra={
                    "channel_id": str(evt.channel_id),
                    "tenant_id": str(evt.tenant_id),
                },
            )
            return

        # 物化 IM 的 actor —— 渠道登记的服务账号（不是全局常量）。
        account = ServiceAccount.from_mapping(getattr(channel, "service_account", None))
        if account is None:
            _log.error(
                "channel has no service account registered; dropping event",
                extra={
                    "channel_id": str(evt.channel_id),
                    "tenant_id": str(evt.tenant_id),
                },
            )
            return

        # Open an ephemeral agent_runtime session, create + run a turn,
        # then write the reply via the outbound adapter (best effort).
        try:
            _, final_message, turn_id = await self._run_turn(evt, channel, account)
        except Exception:
            _log.exception(
                "channel dispatch turn failed",
                extra={
                    "tenant_id": str(evt.tenant_id),
                    "channel_id": str(evt.channel_id),
                },
            )
            return

        if not final_message:
            return

        await self._send_reply(
            evt=evt,
            channel_type=getattr(channel, "type", evt.channel_type),
            text=final_message[:4096],
            turn_id=turn_id,
        )

    # ── helpers ──────────────────────────────────────────────────────────

    async def _run_turn(
        self, evt: ChannelMessageReceived, channel: Any, account: ServiceAccount
    ) -> tuple[UUID, str, UUID | None]:
        """Open session, create agent turn, drain to completion."""
        from qzdap_schema.ids import AgentId, UserId

        async def _drive() -> tuple[UUID, str, UUID | None]:
            session_obj = self._open_session()
            async with session_obj as sess:
                svc = self._ar_factory.for_session(sess)
                record_legacy_call("R1")  # IM 每条消息新建临时 session
                session = await svc.create_session().execute(
                    tenant_id=evt.tenant_id,
                    workspace_id=channel.workspace_id,
                    owner_id=UserId(account.user_id),
                    agent_id=AgentId(account.agent_id),
                    agent_version=account.agent_version,
                    metadata={
                        "channel_id": str(evt.channel_id),
                        "channel_type": evt.channel_type,
                        "external_chat_id": evt.external_chat_id,
                    },
                )
                user_input = (
                    f"[channel={evt.channel_type} chat={evt.external_chat_id}] {evt.text_preview}"
                )
                record_legacy_call("X2")  # 第二套 turn 实现
                result = await svc.run_turn_to_completion().execute(
                    tenant_id=evt.tenant_id,
                    workspace_id=channel.workspace_id,
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
        evt: ChannelMessageReceived,
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
            if str(key) == str(channel_type) or (getattr(key, "value", None) == channel_type):
                adapter = candidate
                break
        if adapter is None:
            _log.info(
                "no outbound adapter for channel_type=%s; reply dropped",
                channel_type,
                extra={
                    "channel_id": str(evt.channel_id),
                    "tenant_id": str(evt.tenant_id),
                },
            )
            return
        try:
            metadata: dict[str, str] = {
                "channel_id": str(evt.channel_id),
            }
            if turn_id is not None:
                metadata["turn_id"] = str(turn_id)
            await adapter.send_reply(
                external_chat_id=evt.external_chat_id,
                text=text,
                metadata=metadata,
            )
        except Exception:  # pragma: no cover - defensive
            _log.exception(
                "outbound send_reply failed",
                extra={"channel_id": str(evt.channel_id)},
            )

    @staticmethod
    def _message_key(evt: ChannelMessageReceived) -> str:
        """Stable dedup key from event fields.

        The inbound event lacks ``external_message_id``; combine the
        fields we do have and hash so the tuple fits in the LRU key.
        """
        raw = f"{evt.channel_id}|{evt.external_user_id}|{evt.external_chat_id}|{evt.text_preview}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _evict_dedup(self) -> None:
        while len(self._seen) > self._dedup_window:
            self._seen.popitem(last=False)


__all__ = ["ChannelDispatchSubscriber"]
