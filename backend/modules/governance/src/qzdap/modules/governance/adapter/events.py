"""Governance → EventBus adapter.

Translates ``publish(topic, payload)`` calls from the governance services
into the kernel ``EventEnvelope`` shape, then dispatches via the live
``EventBus``.  Mirrors ``skill.adapter.events.MessagingSkillEventPublisher``.
"""

from __future__ import annotations

import time
from typing import Any
from uuid import UUID, uuid4

from qzdap_kernel.ids import TenantId, WorkspaceId
from qzdap_messaging.bus import EventBus
from qzdap_messaging.domain_event import EventEnvelope


class MessagingEventPublisher:
    def __init__(self, bus: EventBus) -> None:
        self._bus = bus

    async def publish(self, topic: str, payload: dict[str, Any]) -> None:
        # ⚠️ **这里是「裸值 → 品牌 ID」的那道边界** ✓（载荷来自消息总线 ✓）。
        raw_tid = payload.get("tenant_id")
        tenant_id: TenantId
        if raw_tid is not None:
            tenant_id = TenantId(UUID(str(raw_tid)))
        else:
            tenant_id = TenantId(UUID("00000000-0000-0000-0000-000000000000"))
        raw_wid = payload.get("workspace_id")
        workspace_id = (
            WorkspaceId(UUID(str(raw_wid))) if raw_wid is not None else None
        )

        envelope = EventEnvelope(
            event_id=uuid4(),
            event_name=topic,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            occurred_at_ms=int(time.time() * 1000),
            trace_id=None,
            payload=dict(payload),
        )
        await self._bus.publish(envelope)


__all__ = ["MessagingEventPublisher"]
