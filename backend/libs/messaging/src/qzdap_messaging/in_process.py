"""In-process event bus for dev + tests.

Handlers are called sequentially in the order they subscribed. Errors are
caught and logged so one bad subscriber doesn't break the rest.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import AsyncIterator, Awaitable, Callable

from qzdap_messaging.bus import EventBus
from qzdap_messaging.domain_event import EventEnvelope

_log = logging.getLogger("qzdap.messaging")

Handler = Callable[[EventEnvelope], Awaitable[None]]


class InProcessBus(EventBus):
    def __init__(self) -> None:
        self._subs: dict[str, list[Handler]] = defaultdict(list)
        self._started = False

    async def publish(self, envelope: EventEnvelope) -> None:
        handlers = list(self._subs.get(envelope.event_name, []))
        for h in handlers:
            try:
                await h(envelope)
            except Exception:  # noqa: BLE001
                _log.exception(
                    "handler failed", extra={"event_name": envelope.event_name}
                )

    def subscribe(self, event_name: str, handler: Handler) -> None:  # type: ignore[override]
        self._subs[event_name].append(handler)

    async def start(self) -> None:
        self._started = True

    async def stop(self) -> None:
        self._started = False

    async def stream(  # type: ignore[override]
        self, tenant_id: object
    ) -> AsyncIterator[EventEnvelope]:
        # In-process bus has no replay; raise so callers know to use Redis.
        raise NotImplementedError("InProcessBus.stream: subscribe + publish instead")
        yield  # pragma: no cover — keeps AsyncIterator typing
