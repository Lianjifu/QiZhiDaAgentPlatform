"""Event publishers and subscribers for the identity module."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from qzdap_kernel.contextvars import current_trace_id
from qzdap_messaging.bus import EventBus
from qzdap_messaging.domain_event import DomainEvent, EventEnvelope


class IdentityEventPublisher:
    """Wraps a bus to publish events with the right tenant/workspace."""

    def __init__(self, bus: EventBus) -> None:
        self._bus = bus

    async def publish(
        self,
        event: DomainEvent,
        *,
        tenant_id: object,
        workspace_id: object | None = None,
        metadata: dict | None = None,
    ) -> None:
        envelope = EventEnvelope.wrap(
            event,
            tenant_id=tenant_id,  # type: ignore[arg-type]
            workspace_id=workspace_id,  # type: ignore[arg-type]
            trace_id=current_trace_id(),
            metadata=metadata,
        )
        await self._bus.publish(envelope)


# A trivial subscriber registry for unit tests and dev wiring.
_subscribers: dict[str, list[Callable[[EventEnvelope], Awaitable[None]]]] = {}


def register_subscriber(
    event_name: str, handler: Callable[[EventEnvelope], Awaitable[None]]
) -> None:
    _subscribers.setdefault(event_name, []).append(handler)


async def fire_locally(envelope: EventEnvelope) -> None:
    """Process envelope through registered subscribers."""
    for h in _subscribers.get(envelope.event_name, []):
        try:
            await h(envelope)
        except Exception:
            import logging

            logging.getLogger("qzdap.identity").exception("subscriber failed")


# Re-export to make `asyncio` use obvious to readers
_ = asyncio
