"""Tests for messaging (in-process only — Redis stream is integration-only)."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from qzdap_messaging.domain_event import DomainEvent, EventEnvelope
from qzdap_messaging.in_process import InProcessBus


@dataclass(slots=True)
class FakeEvent(DomainEvent):
    value: int = 1

    def _as_payload_dict(self) -> dict:
        return {"value": self.value}


@pytest.mark.asyncio
async def test_in_process_publish_invokes_handlers() -> None:
    bus = InProcessBus()
    received: list[EventEnvelope] = []

    async def handler(env: EventEnvelope) -> None:
        received.append(env)

    bus.subscribe("FakeEvent", handler)
    env = EventEnvelope.wrap(
        FakeEvent(value=42),
        tenant_id=_uuid(),
        workspace_id=None,
        trace_id=None,
    )
    await bus.publish(env)
    assert len(received) == 1
    assert received[0].event_name == "FakeEvent"
    assert received[0].payload == {"value": 42}


@pytest.mark.asyncio
async def test_failed_handler_does_not_break_others() -> None:
    bus = InProcessBus()
    received: list[int] = []

    async def bad(env: EventEnvelope) -> None:
        raise RuntimeError("boom")

    async def good(env: EventEnvelope) -> None:
        received.append(1)

    bus.subscribe("FakeEvent", bad)
    bus.subscribe("FakeEvent", good)
    env = EventEnvelope.wrap(
        FakeEvent(),
        tenant_id=_uuid(),
        workspace_id=None,
        trace_id=None,
    )
    await bus.publish(env)  # does not raise
    assert received == [1]


def _uuid():
    from uuid import uuid4

    return uuid4()
