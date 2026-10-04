"""Audit subscriber — wires the AuditRecorder to the EventBus.

Lifespan calls ``install(event_bus, recorder)`` to register handlers
for every topic returned by ``recorder.topics()``.  The handler is
``recorder.handle`` itself; the recorder swallows them.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable, Coroutine
from typing import Any

from qzdap.modules.governance.application.audit_recorder import AuditRecorder

SubscriberHandler = Callable[[Any], Coroutine[Any, Any, None]]


async def _subscribe(event_bus: Any, topic: str, handler: Any) -> None:
    """``EventBus.subscribe`` is sync in the in-process adapter and
    async in redis_stream / kafka adapters; await transparently."""
    result = event_bus.subscribe(topic, handler)
    if inspect.isawaitable(result):
        await result


async def install(
    event_bus: Any,
    recorder: AuditRecorder,
    *,
    cache_invalidator: Callable[[Any], None] | None = None,
) -> None:
    """Subscribe the recorder to its topics; invalidate cache on
    governance.policy.* mutations.

    ``event_bus`` must expose ``subscribe(topic, handler)`` (sync or async).
    """
    handler = recorder.handle

    # business events; recorder already includes governance.* topics so
    # cache invalidation hooks into the recorder's own handler below.
    seen: set[str] = set()
    for topic in recorder.topics():
        if topic in seen:
            continue
        seen.add(topic)
        await _subscribe(event_bus, topic, handler)

    # policy lifecycle → invalidate evaluator cache.
    # We register a separate handler rather than wrap ``handler`` so the
    # cache invalidation runs even if the audit recorder skips a payload.
    # The cache-invalidator subscribes alongside the recorder (same topic
    # = two handlers); we don't dedupe across handler kinds.
    if cache_invalidator is not None:

        async def _policy_changed(envelope: Any) -> None:
            payload = (
                getattr(envelope, "payload", None)
                if not isinstance(envelope, dict)
                else envelope
            )
            raw_tid = payload.get("tenant_id") if isinstance(payload, dict) else None
            if raw_tid is None:
                return
            try:
                from uuid import UUID

                tenant_id = UUID(str(raw_tid))
            except (TypeError, ValueError):
                return
            cache_invalidator(tenant_id)

        for topic in (
            "governance.policy.created",
            "governance.policy.updated",
            "governance.policy.deleted",
        ):
            await _subscribe(event_bus, topic, _policy_changed)


__all__ = ["install"]
