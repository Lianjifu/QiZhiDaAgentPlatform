"""Messaging adapter for evaluation events."""

from __future__ import annotations

import logging
from typing import Any

from qzdap_messaging.domain_event import EventEnvelope

from qzdap.modules.evaluation.domain.events import (
    EvalRunCompleted,
    EvalRunFailed,
    EvalRunStarted,
)

logger = logging.getLogger(__name__)


class MessagingEvaluationEventPublisher:
    """Wraps evaluation events into EventEnvelope and dispatches via bus."""

    def __init__(self, bus: Any) -> None:
        self._bus = bus

    async def publish(self, event: object) -> None:
        topic = getattr(event, "TOPIC", None)
        if topic is None:
            logger.warning("event %s has no TOPIC; dropped", type(event).__name__)
            return
        tenant_id = getattr(event, "tenant_id", None)
        workspace_id = getattr(event, "workspace_id", None)
        trace_id = getattr(event, "trace_id", None)
        try:
            envelope = EventEnvelope.wrap(
                event,  # type: ignore[arg-type]
                tenant_id=tenant_id,  # type: ignore[arg-type]
                workspace_id=workspace_id,
                trace_id=trace_id,
            )
            await self._bus.publish(envelope)
        except Exception:  # pragma: no cover - defensive
            logger.exception("publish %s failed", type(event).__name__)


__all__ = [
    "EvalRunCompleted",
    "EvalRunFailed",
    "EvalRunStarted",
    "MessagingEvaluationEventPublisher",
]
