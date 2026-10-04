"""Domain event base + envelope.

``DomainEvent`` lives in the kernel package because every aggregate, in
every module, raises events that descend from it. We re-export it here
for convenience so callers using ``qzdap_messaging.domain_event`` keep
working, but new code should import from ``qzdap_kernel``.

The application layer wraps concrete ``DomainEvent`` instances into an
``EventEnvelope`` and hands the envelope to the bus for dispatch.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

from qzdap_kernel.events import DomainEvent

__all__ = ["DomainEvent", "EventEnvelope"]


@dataclass(slots=True)
class EventEnvelope:
    """Wire-level wrapper around a DomainEvent."""

    event_id: UUID
    event_name: str
    tenant_id: UUID
    workspace_id: UUID | None
    occurred_at_ms: int
    trace_id: str | None
    payload: dict[str, Any]
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def wrap(
        cls,
        event: DomainEvent,
        *,
        tenant_id: UUID,
        workspace_id: UUID | None,
        trace_id: str | None,
        metadata: dict[str, Any] | None = None,
    ) -> EventEnvelope:
        # `dataclasses.asdict` would work for dataclass events; we fall back
        # to `__dict__` for plain classes and use `_as_payload_dict` if defined.
        payload = (
            event._as_payload_dict()
            if hasattr(event, "_as_payload_dict")
            else _safe_asdict(event)
        )
        return cls(
            event_id=uuid4(),
            event_name=event.event_name,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            occurred_at_ms=int(time.time() * 1000),
            trace_id=trace_id,
            payload=payload,
            metadata=metadata or {},
        )


def _safe_asdict(obj: object) -> dict[str, Any]:
    """Best-effort dict for plain event objects."""
    if hasattr(obj, "__dict__"):
        return {k: v for k, v in obj.__dict__.items() if not k.startswith("_")}
    return {"value": str(obj)}
