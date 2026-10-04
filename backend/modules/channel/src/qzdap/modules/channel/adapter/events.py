"""Messaging-backed channel event publisher.

Wraps the in-process :class:`qzdap_messaging.bus.EventBus` so the channel
service can publish business events through the
:class:`ChannelEventPublisher` Protocol without importing the bus.

Each call site passes the concrete :class:`DomainEvent` instance plus
actor context; this adapter pulls ``tenant_id`` / ``workspace_id`` off
the event (or actor context), wraps it in an :class:`EventEnvelope`,
and dispatches via the bus. ``event_name`` is the PascalCase class
name — matching every other module that uses
``EventEnvelope.wrap(event)`` — so the audit recorder's PascalCase
subscription keys match.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from qzdap_messaging.domain_event import EventEnvelope

if TYPE_CHECKING:
    from uuid import UUID

    from qzdap_messaging.bus import EventBus

logger = logging.getLogger(__name__)


class MessagingChannelEventPublisher:
    def __init__(self, bus: EventBus) -> None:
        self._bus = bus

    async def publish(
        self,
        event: object,
        *,
        tenant_id: UUID,
        workspace_id: UUID | None,
        trace_id: str | None = None,
    ) -> None:
        envelope = EventEnvelope.wrap(
            event,  # type: ignore[arg-type]
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            trace_id=trace_id,
        )
        try:
            await self._bus.publish(envelope)
        except Exception:  # pragma: no cover — defensive
            logger.exception(
                "channel event bus publish failed: event=%s",
                type(event).__name__,
            )


__all__ = ["MessagingChannelEventPublisher"]
