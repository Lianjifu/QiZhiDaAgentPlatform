"""Channel → agent_runtime dispatch subscriber.

Subscribes to :class:`ChannelMessageReceived` events on the in-process
event bus, opens an ephemeral system-actor session, runs a single
agent turn through :class:`RunTurnCompletionUseCase`, and writes the
final assistant message back through the outbound adapter registered
for the channel's ``channel_type``.

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

from qzdap.modules.channel.domain.events import ChannelMessageReceived

if TYPE_CHECKING:
    from qzdap.modules.channel.application.ports import (
        ChannelRepository,
        OutboundAdapter,
    )

_log = logging.getLogger("qzdap.channel.dispatch")

# Deterministic UUIDs reserved for the system actor that drives channel
# messages through agent_runtime. Stable across restarts so the same
# logical actor always owns the row ownership column.
SYSTEM_USER_ID: UUID = UUID("00000000-0000-0000-0000-00000000c0c0")
SYSTEM_AGENT_ID: UUID = UUID("00000000-0000-0000-0000-00000000c0c1")
SYSTEM_AGENT_VERSION = "channel-router-1.0.0"

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
        """Domain-level dispatch."""
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

        # Open an ephemeral agent_runtime session, create + run a turn,
        # then write the reply via the outbound adapter (best effort).
        try:
            _, final_message, turn_id = await self._run_turn(evt, channel)
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
        self, evt: ChannelMessageReceived, channel: Any
    ) -> tuple[UUID, str, UUID | None]:
        """Open session, create agent turn, drain to completion."""
        from qzdap_schema.ids import AgentId, UserId

        async def _drive() -> tuple[UUID, str, UUID | None]:
            session_obj = self._open_session()
            async with session_obj as sess:
                svc = self._ar_factory.for_session(sess)
                session = await svc.create_session().execute(
                    tenant_id=evt.tenant_id,
                    workspace_id=channel.workspace_id,
                    owner_id=UserId(SYSTEM_USER_ID),
                    agent_id=AgentId(SYSTEM_AGENT_ID),
                    agent_version=SYSTEM_AGENT_VERSION,
                    metadata={
                        "channel_id": str(evt.channel_id),
                        "channel_type": evt.channel_type,
                        "external_chat_id": evt.external_chat_id,
                    },
                )
                user_input = (
                    f"[channel={evt.channel_type} chat={evt.external_chat_id}] {evt.text_preview}"
                )
                result = await svc.run_turn_to_completion().execute(
                    tenant_id=evt.tenant_id,
                    workspace_id=channel.workspace_id,
                    owner_id=UserId(SYSTEM_USER_ID),
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


__all__ = [
    "SYSTEM_AGENT_ID",
    "SYSTEM_AGENT_VERSION",
    "SYSTEM_USER_ID",
    "ChannelDispatchSubscriber",
]
