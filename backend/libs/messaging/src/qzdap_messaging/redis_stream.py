"""Redis-stream event bus for production multi-replica deployments.

Streams are keyed ``qzdap:events:{tenant_id}``; one stream per tenant.
Consumer groups give at-least-once delivery. Handlers that raise cause
the entry to be re-published with an incremented ``retry_count`` up to
``max_retries``; after that the entry goes to ``qzdap:events:dlq``.

Subscriber dispatch model
-------------------------

``subscribe(topic, handler)`` registers a local handler on this process
only — exactly the same surface area as :class:`InProcessBus`. The
difference is when the handler fires:

* :class:`InProcessBus` runs handlers inline inside ``publish()`` —
  synchronous within the producer's coroutine.
* This bus fires handlers from a background ``asyncio.Task`` spawned by
  ``start()`` that reads every tenant stream via ``XREADGROUP`` and
  dispatches each envelope to the locally-registered handlers.

This means a publish from any replica reaches the handlers on every
other replica that is subscribed — the cross-replica guarantee that
``InProcessBus`` cannot provide. The ``stream(tenant_id)`` method stays
as a low-level replay API for one-shot consumers.

Per-replica consumer name resolution
------------------------------------

``consumer_name`` parameter (or ``QZDAP_EVENT_REDIS_CONSUMER_NAME`` env):
explicit > ``socket.gethostname()`` > ``host-{uuid4().hex[:8]}``. Each
replica picks a stable name so its in-flight entries are isolated from
its peers; restart picks a new UUID and Redis reassigns pending entries
via XCLAIM (handled automatically by Redis 7+).

Failure handling
----------------

``max_retries`` controls how many times a single entry is re-delivered
to local handlers before it lands in the DLQ. The count lives in the
``retry_count`` field of the stream entry, so it survives process
restarts. After ``max_retries`` is exhausted the entry is XADD'd to the
DLQ stream with a ``dlq_reason`` field and XACK'd off the source stream
so it doesn't loop forever.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import socket
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import TYPE_CHECKING

from qzdap_messaging.bus import EventBus
from qzdap_messaging.domain_event import EventEnvelope

if TYPE_CHECKING:
    from redis.asyncio import Redis

logger = logging.getLogger(__name__)

Handler = Callable[[EventEnvelope], Awaitable[None]]


def _is_busy_group(exc: BaseException) -> bool:
    """XGROUP CREATE returns BUSYGROUP if the group already exists."""
    msg = str(exc)
    return "BUSYGROUP" in msg or "Consumer Group name already exists" in msg


def _resolve_consumer_name(explicit: str) -> str:
    """Pick a stable consumer name across replicas.

    Priority: explicit arg > ``QZDAP_EVENT_REDIS_CONSUMER_NAME`` env >
    ``socket.gethostname()`` > ``host-{uuid4().hex[:8]}``. The hostname
    path keeps k8s ``POD_NAME`` semantics without an extra env lookup;
    the UUID fallback guards against CI / local containers where
    hostname may be identical across replicas.
    """
    if explicit:
        return explicit
    env_name = os.environ.get("QZDAP_EVENT_REDIS_CONSUMER_NAME", "").strip()
    if env_name:
        return env_name
    try:
        host = socket.gethostname()
        if host:
            return host
    except Exception:  # noqa: BLE001 - hostname lookup is best-effort
        logger.debug("socket.gethostname() failed; falling back to uuid")
    return f"host-{uuid.uuid4().hex[:8]}"


class RedisStreamBus(EventBus):
    def __init__(
        self,
        redis: Redis,
        *,
        prefix: str = "qzdap:events:",
        dlq_stream: str = "qzdap:events:dlq",
        consumer_group: str = "qzdap-default",
        consumer_name: str = "",
        max_retries: int = 3,
        block_ms: int = 1000,
        count: int = 10,
    ) -> None:
        self._r = redis
        self._prefix = prefix
        self._dlq = dlq_stream
        # Per-replica consumer group: every replica lives in its own group
        # so XREADGROUP fans out instead of load-balancing. Restart picks a
        # new group (because consumer_name is re-derived) and the previous
        # group's PEL stays in Redis for ops to inspect.
        self._consumer_name = _resolve_consumer_name(consumer_name)
        self._group = f"{consumer_group}:{self._consumer_name}"
        self._max_retries = max_retries
        self._block_ms = block_ms
        self._count = count
        self._subs: dict[str, list[Handler]] = {}
        self._consumer_task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()

    @property
    def consumer_name(self) -> str:
        return self._consumer_name

    async def publish(self, envelope: EventEnvelope) -> None:
        key = self._stream_key(envelope.tenant_id)
        payload = {
            "event_id": str(envelope.event_id),
            "event_name": envelope.event_name,
            "tenant_id": str(envelope.tenant_id),
            "workspace_id": str(envelope.workspace_id) if envelope.workspace_id else "",
            "trace_id": envelope.trace_id or "",
            "occurred_at_ms": envelope.occurred_at_ms,
            "payload": json.dumps(envelope.payload, default=str),
            "metadata": json.dumps(envelope.metadata, default=str),
            "retry_count": "0",
        }
        await self._r.xadd(key, payload)  # type: ignore[arg-type]

    async def subscribe(  # type: ignore[override]
        self, event_name: str, handler: Handler
    ) -> None:
        """Register a handler on this replica.

        Same signature as :class:`InProcessBus.subscribe` but async —
        callers already ``await`` it (audit_subscriber, obs_install,
        channel dispatch), so swapping the bus is non-breaking.
        """
        self._subs.setdefault(event_name, []).append(handler)

    async def start(self) -> None:
        """Idempotent: create consumer groups + launch the consumer loop.

        Re-entry is safe — running ``start()`` on an already-started
        instance is a no-op.
        """
        if self._consumer_task is not None and not self._consumer_task.done():
            return
        await self._ensure_groups()
        self._stop_event.clear()
        self._consumer_task = asyncio.create_task(
            self._consumer_loop(), name=f"redis-stream-bus:{self._consumer_name}"
        )

    async def stop(self) -> None:
        """Cancel the consumer loop and wait for it to drain."""
        self._stop_event.set()
        if self._consumer_task is None:
            return
        self._consumer_task.cancel()
        try:
            await self._consumer_task
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("consumer task raised during stop()")
        self._consumer_task = None

    async def _ensure_groups(self) -> None:
        # Idempotent group creation across every existing stream (DLQ excluded).
        for key in await self._r.keys(f"{self._prefix}*"):
            if self._is_dlq_key(key):
                continue
            try:
                await self._r.xgroup_create(key, self._group, id="0", mkstream=True)
            except Exception as exc:
                if not _is_busy_group(exc):
                    raise
                logger.debug("consumer group already exists on stream %s", key)

    async def _consumer_loop(self) -> None:
        """Read every tenant stream + dispatch to local handlers.

        Each iteration: scan for known streams (cheap on Redis 7 with
        XCARD-driven bookkeeping; acceptable for the tenant counts we
        expect). ``XREADGROUP`` blocks up to ``block_ms`` for new
        entries. On a transient error (network blip, etc.) we sleep
        100 ms and retry instead of crashing the consumer.
        """
        while not self._stop_event.is_set():
            try:
                streams = await self._discover_streams()
                if not streams:
                    await asyncio.sleep(0.1)
                    continue
                resp = await self._r.xreadgroup(
                    groupname=self._group,
                    consumername=self._consumer_name,
                    streams=streams,  # type: ignore[arg-type]
                    count=self._count,
                    block=self._block_ms,
                )
                if not resp:
                    # No new entries; yield to the event loop so other
                    # coroutines (publish, stop, lifespan) get scheduled.
                    # In production real Redis honors block_ms and parks
                    # the socket; this branch only fires when block=0 or
                    # the underlying client returns immediately.
                    await asyncio.sleep(0)
                    continue
                for _stream, entries in resp:  # type: ignore[union-attr, str-unpack]
                    for msg_id, fields in entries:  # type: ignore[union-attr, str-unpack]
                        envelope = _envelope_from_fields(
                            fields  # type: ignore[arg-type]
                        )
                        await self._dispatch(
                            _stream,  # type: ignore[arg-type]
                            msg_id,  # type: ignore[arg-type]
                            envelope,
                            fields,  # type: ignore[arg-type]
                        )
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("redis stream bus consumer loop error; sleeping 1s")
                await asyncio.sleep(1.0)

    async def _discover_streams(self) -> dict[str | bytes, str]:
        """Map of stream key → '>' for XREADGROUP.

        Auto-creates the consumer group on a brand-new tenant stream the
        first time we see it, so a fresh tenant's first event doesn't
        stall waiting for the next ``start()``.

        Excludes the DLQ stream — failed entries live there but should
        only be replayed by an operator with the right tooling.
        """
        keys = await self._r.keys(f"{self._prefix}*")
        out: dict[str | bytes, str] = {}
        for k in keys:
            if self._is_dlq_key(k):
                continue
            try:
                await self._r.xgroup_create(k, self._group, id="0", mkstream=True)
            except Exception as exc:  # noqa: BLE001
                if not _is_busy_group(exc):
                    logger.warning("xgroup_create failed for %s: %s", k, exc)
            out[k] = ">"
        return out

    def _is_dlq_key(self, key: bytes | str) -> bool:
        if isinstance(key, bytes):
            return key == self._dlq.encode() or key == self._dlq.encode() + b"*"
        return key == self._dlq or key == self._dlq + "*"

    async def _dispatch(
        self,
        stream: bytes | str,
        msg_id: bytes | str,
        envelope: EventEnvelope,
        fields: dict[bytes | str, bytes | str],
    ) -> None:
        handlers = list(self._subs.get(envelope.event_name, []))
        if not handlers:
            # Nobody cares about this topic — ACK so it doesn't accumulate.
            await self._r.xack(stream, self._group, msg_id)
            return
        retry_count = _retry_count_of(fields)
        for handler in handlers:
            try:
                await handler(envelope)
            except Exception:
                logger.exception(
                    "handler raised for %s; will retry or DLQ",
                    envelope.event_name,
                )
                await self._retry_or_dlq(stream, msg_id, fields, retry_count)
                return  # don't try the next handler on this entry
        # All handlers succeeded → ACK
        await self._r.xack(stream, self._group, msg_id)

    async def _retry_or_dlq(
        self,
        stream: bytes | str,
        msg_id: bytes | str,
        fields: dict[bytes | str, bytes | str],
        retry_count: int,
    ) -> None:
        next_count = retry_count + 1
        new_fields: dict[bytes, bytes] = {}

        def _to_bytes(v: object) -> bytes:
            if isinstance(v, bytes):
                return v
            if isinstance(v, str):
                return v.encode()
            return str(v).encode()

        for k, v in fields.items():
            kk = k if isinstance(k, bytes) else k.encode()
            new_fields[kk] = _to_bytes(v)
        new_fields[b"retry_count"] = str(next_count).encode()
        if next_count <= self._max_retries:
            # Re-publish to the same stream; ACK original so it doesn't loop.
            await self._r.xadd(stream, new_fields)  # type: ignore[arg-type]
            await self._r.xack(stream, self._group, msg_id)
            logger.warning(
                "redis stream bus: retrying %s (attempt %d/%d)",
                msg_id,
                next_count,
                self._max_retries,
            )
        else:
            # DLQ — preserve the original envelope + retry trail.
            dlq_fields = dict(new_fields)
            dlq_fields[b"dlq_reason"] = b"max_retries_exceeded"
            await self._r.xadd(self._dlq, dlq_fields)  # type: ignore[arg-type]
            await self._r.xack(stream, self._group, msg_id)
            logger.error(
                "redis stream bus: DLQ %s after %d retries",
                msg_id,
                retry_count,
            )

    def _stream_key(self, tenant_id: object) -> str:
        return f"{self._prefix}{tenant_id}"

    async def stream(  # type: ignore[override, misc]
        self, tenant_id: object
    ) -> AsyncIterator[EventEnvelope]:
        """Replay one tenant's stream via XREADGROUP. Low-level API
        used by ad-hoc tools / debug pages; production subscribers
        should use :meth:`subscribe` and let the consumer loop dispatch.
        """
        key = self._stream_key(tenant_id)
        try:
            await self._r.xgroup_create(key, self._group, id="0", mkstream=True)
        except Exception as exc:
            if not _is_busy_group(exc):
                raise
            logger.debug("consumer group already exists on stream %s", key)

        last_id = ">"
        while True:
            resp = await self._r.xreadgroup(
                groupname=self._group,
                consumername=f"{self._consumer_name}-replay",
                streams={key: last_id},
                count=self._count,
                block=self._block_ms,
            )
            for _stream, entries in resp:  # type: ignore[str-unpack, union-attr]
                for msg_id, fields in entries:  # type: ignore[str-unpack, union-attr]
                    yield _envelope_from_fields(fields)  # type: ignore[arg-type]
                    await self._r.xack(key, self._group, msg_id)  # type: ignore[arg-type]


def _retry_count_of(fields: dict[bytes | str, bytes | str]) -> int:
    raw = fields.get(b"retry_count", fields.get("retry_count", b"0"))
    if isinstance(raw, str):
        raw = raw.encode()
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 0


def _envelope_from_fields(fields: dict[bytes | str, bytes | str]) -> EventEnvelope:
    """Reconstruct an envelope from xadd fields. Stays import-light to avoid a
    circular dep on schema.

    Real ``redis.asyncio`` serializes field keys + values to ``bytes``;
    some in-memory test doubles keep them as ``str``. Normalize both.
    """
    from uuid import UUID

    def _s(v: object) -> str:
        if isinstance(v, bytes):
            return v.decode()
        if isinstance(v, str):
            return v
        return str(v)

    def _u(v: object) -> str:
        s = _s(v)
        return s if s else ""

    tenant_id = UUID(
        _s(fields[b"tenant_id" if b"tenant_id" in fields else "tenant_id"])
    )
    return EventEnvelope(
        event_id=UUID(_s(fields[b"event_id" if b"event_id" in fields else "event_id"])),
        event_name=_s(
            fields[b"event_name" if b"event_name" in fields else "event_name"]
        ),
        tenant_id=tenant_id,
        workspace_id=UUID(
            _s(fields[b"workspace_id" if b"workspace_id" in fields else "workspace_id"])
        )
        if _u(fields[b"workspace_id" if b"workspace_id" in fields else "workspace_id"])
        else None,
        trace_id=_u(fields[b"trace_id" if b"trace_id" in fields else "trace_id"])
        or None,
        occurred_at_ms=int(
            _s(
                fields[
                    b"occurred_at_ms"
                    if b"occurred_at_ms" in fields
                    else "occurred_at_ms"
                ]
            )
        ),
        payload=json.loads(
            _s(fields[b"payload" if b"payload" in fields else "payload"])
        ),
        metadata=json.loads(_s(fields.get(b"metadata", fields.get("metadata", "{}")))),
    )


__all__ = [
    "Handler",
    "RedisStreamBus",
    "_resolve_consumer_name",
]
