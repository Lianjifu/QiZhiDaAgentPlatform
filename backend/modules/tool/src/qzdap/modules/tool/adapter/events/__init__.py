"""Event publisher for the tool module.

Wraps `EventBus` so use cases can pass bare `DomainEvent`s; the publisher
attaches request-scoped metadata (tenant_id, workspace_id, trace_id) into
an `EventEnvelope` before handing to the bus.
"""

from __future__ import annotations

from uuid import UUID

from qzdap_kernel.events import DomainEvent
from qzdap_messaging.bus import EventBus
from qzdap_messaging.domain_event import EventEnvelope

from qzdap.modules.tool.application.ports import EventPublisher


class ToolEventPublisher(EventPublisher):
    def __init__(self, bus: EventBus) -> None:
        self._bus = bus

    async def publish(
        self,
        event: DomainEvent,
        *,
        tenant_id: UUID,
        workspace_id: UUID | None,
        trace_id: str | None = None,
    ) -> None:
        envelope = EventEnvelope.wrap(
            event,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            trace_id=trace_id,
        )
        await self._bus.publish(envelope)


__all__ = ["ToolEventPublisher"]
