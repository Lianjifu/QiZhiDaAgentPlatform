"""Event publisher adapter — wraps `qzdap_messaging.EventBus.publish` with
`EventEnvelope.wrap(...)` so use cases can publish bare `DomainEvent`s.
"""

from __future__ import annotations

from qzdap.modules.agent_runtime.application.ports import EventPublisher
from qzdap_kernel.contextvars import current_trace_id
from qzdap_kernel.events import DomainEvent
from qzdap_kernel.ids import TenantId, WorkspaceId
from qzdap_messaging.bus import EventBus
from qzdap_messaging.domain_event import EventEnvelope


class AgentRuntimeEventPublisher(EventPublisher):
    def __init__(self, bus: EventBus) -> None:
        self._bus = bus

    async def publish(
        self,
        event: DomainEvent,
        *,
        tenant_id: TenantId,
        workspace_id: WorkspaceId | None,
        trace_id: str | None = None,
    ) -> None:
        envelope = EventEnvelope.wrap(
            event,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            trace_id=trace_id or current_trace_id(),
        )
        await self._bus.publish(envelope)
