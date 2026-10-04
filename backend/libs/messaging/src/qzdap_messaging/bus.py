"""EventBus Protocol."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol

from qzdap_messaging.domain_event import EventEnvelope


class EventBus(Protocol):
    async def publish(self, envelope: EventEnvelope) -> None: ...
    def subscribe(self, event_name: str, handler: object) -> None: ...
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    async def stream(self, tenant_id: object) -> AsyncIterator[EventEnvelope]: ...


class NullBus:
    """A bus that drops every event. Useful for tests + dry runs."""

    async def publish(self, envelope: EventEnvelope) -> None:
        return None

    def subscribe(self, event_name: str, handler: object) -> None:
        return None

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    async def stream(self, tenant_id: object) -> AsyncIterator[EventEnvelope]:
        if False:  # pragma: no cover — never iterates
            yield
        return
