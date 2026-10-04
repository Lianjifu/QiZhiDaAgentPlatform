"""Kafka audit bus — producer + consumer for the audit pipeline.

Replaces the synchronous ``SqlAuditLogAdapter.append()`` call in the
request hot path with a Kafka producer → topic → consumer → SQL flow.

* ``KafkaAuditPublisher`` implements the ``AuditLogPort`` Protocol (so
  ``AuditRecorder`` is unaware of the swap). ``_scrub()`` runs here
  before ``send_and_wait`` so the topic payload is already compliant.
* ``KafkaAuditConsumer`` runs as a background ``asyncio.Task`` and
  drains the topic back into ``SqlAuditLogAdapter``. Co-located by
  default (``QZDAP_AUDIT_CONSUMER_ENABLED=true``); flip it off in k8s
  when scaling horizontally so only one replica drains.
* At-least-once delivery: ``enable_auto_commit=False``, batch commit
  per TopicPartition. Idempotency on redelivery is deferred to A6
  (``audit_log.idempotency_key`` UNIQUE column).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import socket
import time
import uuid
from typing import Any, Protocol, runtime_checkable

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from aiokafka.errors import KafkaConnectionError

_log = logging.getLogger(__name__)


# ── secret scrubbing (producer-side, single redaction point) ──────────────


SENSITIVE = frozenset({"password", "api_key", "secret", "token", "authorization"})


def scrub(payload: dict[str, Any]) -> dict[str, Any]:
    """Producer-side redaction — topic payload is 'safe'.

    Rules:
    * Lower-case key in ``SENSITIVE`` and not ending with ``_ref`` → replaced
      with ``<key>_redacted = "***"``. ``secrets_ref`` pointers are kept
      verbatim so callers can still resolve them via the vault.
    """
    out: dict[str, Any] = {}
    for k, v in payload.items():
        if k.lower() in SENSITIVE and not k.endswith("_ref"):
            out[k + "_redacted"] = "***"
        else:
            out[k] = v
    return out


# ── serializer helpers (defensive about UUID / datetime) ───────────────────


def _key_serializer(k: Any) -> bytes | None:
    if k is None:
        return None
    return str(k).encode("utf-8")


def _value_serializer(v: Any) -> bytes:
    return json.dumps(v, default=str).encode("utf-8")


def _key_deserializer(b: bytes | None) -> str | None:
    if b is None:
        return None
    return b.decode("utf-8")


def _value_deserializer(b: bytes | None) -> dict[str, Any]:
    if b is None:
        return {}
    return json.loads(b.decode("utf-8"))


# ── consumer group resolution (mirror redis_stream pattern) ────────────────


def resolve_consumer_group(explicit: str = "") -> str:
    """explicit arg > env > hostname > uuid4 fallback."""
    if explicit:
        return explicit
    env = os.environ.get("QZDAP_AUDIT_KAFKA_CONSUMER_GROUP")
    if env:
        return env
    try:
        return f"qzdap-audit-{socket.gethostname()}"
    except OSError:
        return f"qzdap-audit-{uuid.uuid4().hex[:8]}"


# ── producer ───────────────────────────────────────────────────────────────


class KafkaAuditPublisher:
    """AuditLogPort implementation that produces to Kafka.

    Lifecycle: lifespan calls ``await producer.start()`` once before the
    recorder sees any events; ``await producer.stop()`` on shutdown.
    ``append()`` is fire-and-await with retry+DLQ on persistent failure.
    """

    def __init__(
        self,
        *,
        bootstrap_servers: str,
        topic: str,
        dlq_topic: str,
        max_retries: int = 3,
        request_timeout_ms: int = 5000,
    ) -> None:
        self._bootstrap = bootstrap_servers
        self._topic = topic
        self._dlq_topic = dlq_topic
        self._max_retries = max_retries
        self._timeout_ms = request_timeout_ms
        self._producer: AIOKafkaProducer | None = None
        self._start_lock = asyncio.Lock()
        self._started: bool = False

    async def start(self) -> None:
        async with self._start_lock:
            if self._producer is not None:
                self._started = True
                return
            try:
                self._producer = AIOKafkaProducer(
                    bootstrap_servers=self._bootstrap,
                    key_serializer=_key_serializer,
                    value_serializer=_value_serializer,
                    request_timeout_ms=self._timeout_ms,
                    acks="all",
                )
                await self._producer.start()
            except KafkaConnectionError as exc:
                # Audit must not raise back to the caller (P5). The retry+DLQ
                # path in ``append()`` will re-attempt on every send; if the
                # broker stays down for the whole retry window, ``append()``
                # logs and returns the body without raising. Mark _started
                # anyway so append() distinguishes "start() called" from
                # "start() never called".
                self._producer = None
                self._started = True
                _log.warning(
                    "kafka audit producer start failed bootstrap=%s topic=%s err=%s",
                    self._bootstrap,
                    self._topic,
                    exc,
                )
                return
            self._started = True
            _log.info(
                "kafka audit producer started bootstrap=%s topic=%s",
                self._bootstrap,
                self._topic,
            )

    async def stop(self) -> None:
        async with self._start_lock:
            if self._producer is None:
                return
            await self._producer.stop()
            self._producer = None
            _log.info("kafka audit producer stopped")

    @property
    def topic(self) -> str:
        return self._topic

    @property
    def dlq_topic(self) -> str:
        return self._dlq_topic

    @property
    def started(self) -> bool:
        return self._producer is not None

    async def append(
        self,
        *,
        tenant_id: Any,
        actor_id: Any | None,
        event_type: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Produce one audit event with retry+DLQ. Returns the serialized body.

        Audit must never raise back to the EventBus handler: the
        ``AuditRecorder.handle()`` already wraps the call in try/except.
        Here we still try-DLQ before giving up so a recovered broker
        doesn't drop the event silently.
        """
        if not self._started:
            raise RuntimeError(
                "KafkaAuditPublisher not started — call start() in lifespan"
            )

        body: dict[str, Any] = {
            "tenant_id": str(tenant_id),
            "actor_id": str(actor_id) if actor_id is not None else None,
            "event_type": event_type,
            "payload": scrub(payload),
            "produced_at_ms": int(time.time() * 1000),
            "schema_version": 1,
        }
        key = body["tenant_id"]

        # Broker was never reachable (start() failed at boot) — log + return
        # body without raising. Audit must never fail back to caller.
        if self._producer is None:
            _log.error(
                "kafka audit publisher not started topic=%s event_type=%s; "
                "dropping event silently",
                self._topic,
                event_type,
            )
            return body

        attempts = 0
        last_exc: Exception | None = None
        while attempts <= self._max_retries:
            try:
                await self._producer.send_and_wait(self._topic, value=body, key=key)
                return body
            except Exception as exc:  # noqa: BLE001 — audit must retry on any broker error
                attempts += 1
                last_exc = exc
                _log.warning(
                    "kafka audit publish failed attempt=%d topic=%s err=%s",
                    attempts,
                    event_type,
                    exc,
                )

        # All retries exhausted → DLQ.
        try:
            await self._producer.send_and_wait(
                self._dlq_topic,
                value={**body, "dlq_reason": repr(last_exc)},
                key=key,
            )
            _log.error(
                "kafka audit event sent to DLQ topic=%s dlq=%s err=%s",
                self._topic,
                self._dlq_topic,
                last_exc,
            )
        except Exception as exc:  # noqa: BLE001 — DLQ best-effort; nothing else to do
            _log.error(
                "kafka audit DLQ publish also failed topic=%s err=%s",
                self._topic,
                exc,
            )
        return body


# ── consumer ───────────────────────────────────────────────────────────────


@runtime_checkable
class _ConsumerAuditPort(Protocol):
    """What the consumer needs from an AuditLogPort — narrow surface."""

    async def append(
        self,
        *,
        tenant_id: Any,
        actor_id: Any | None,
        event_type: str,
        payload: dict[str, Any],
    ) -> Any: ...


class KafkaAuditConsumer:
    """Background consumer: Kafka topic → audit_port.

    Mirrors ``RedisStreamBus._consumer_loop``: ``asyncio.Task`` +
    ``asyncio.Event`` stop signal + batch dispatch. ``enable_auto_commit``
    is False so a crash mid-batch redelivers (at-least-once).
    """

    def __init__(
        self,
        *,
        bootstrap_servers: str,
        topic: str,
        group_id: str,
        audit_port: _ConsumerAuditPort,
        block_ms: int = 1000,
        max_records: int = 50,
    ) -> None:
        self._bootstrap = bootstrap_servers
        self._topic = topic
        self._group = group_id
        self._audit_port = audit_port
        self._block_ms = block_ms
        self._max_records = max_records
        self._consumer: AIOKafkaConsumer | None = None
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()

    @property
    def group_id(self) -> str:
        return self._group

    @property
    def task(self) -> asyncio.Task[None] | None:
        return self._task

    async def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._consumer = AIOKafkaConsumer(
            self._topic,
            bootstrap_servers=self._bootstrap,
            group_id=self._group,
            enable_auto_commit=False,
            auto_offset_reset="earliest",
            key_deserializer=_key_deserializer,
            value_deserializer=_value_deserializer,
        )
        await self._consumer.start()
        self._stop_event.clear()
        self._task = asyncio.create_task(
            self._loop(), name=f"kafka-audit-{self._group}"
        )
        _log.info(
            "kafka audit consumer started bootstrap=%s topic=%s group=%s",
            self._bootstrap,
            self._topic,
            self._group,
        )

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=5.0)
            except TimeoutError:
                self._task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await self._task
            self._task = None
        if self._consumer is not None:
            await self._consumer.stop()
            self._consumer = None
        _log.info("kafka audit consumer stopped group=%s", self._group)

    async def _loop(self) -> None:
        assert self._consumer is not None  # for type checker
        consumer = self._consumer
        while not self._stop_event.is_set():
            try:
                msgs = await consumer.getmany(
                    timeout_ms=self._block_ms, max_records=self._max_records
                )
                if not msgs:
                    await asyncio.sleep(0)
                    continue
                for tp, batch in msgs.items():
                    ack_offset = batch[-1].offset + 1
                    for msg in batch:
                        body = msg.value
                        await self._dispatch(body)
                    await consumer.commit({tp: ack_offset})
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 — consumer must survive transient errors
                _log.error("kafka audit consumer loop error: %s", exc)
                await asyncio.sleep(0.5)

    async def _dispatch(self, body: dict[str, Any]) -> None:
        """Convert the on-wire body to AuditLogPort.append kwargs.

        Tolerates missing fields (e.g. ``actor_id=None``, unknown schema
        version) so a future producer evolution doesn't crash the
        consumer.
        """
        from uuid import UUID

        from qzdap_schema.ids import TenantId, UserId

        try:
            tenant_id = TenantId(UUID(str(body["tenant_id"])))
        except (KeyError, TypeError, ValueError) as exc:
            _log.error("audit consumer dropped (bad tenant_id): %s body=%s", exc, body)
            return
        raw_actor = body.get("actor_id")
        actor_id: UserId | None = None
        if raw_actor:
            try:
                actor_id = UserId(UUID(str(raw_actor)))
            except (TypeError, ValueError) as exc:
                _log.warning("audit consumer dropped actor_id=%s: %s", raw_actor, exc)
                actor_id = None
        event_type = str(body.get("event_type") or "unknown")
        payload = body.get("payload") or {}
        await self._audit_port.append(
            tenant_id=tenant_id,
            actor_id=actor_id,
            event_type=event_type,
            payload=payload,
        )


__all__ = [
    "SENSITIVE",
    "KafkaAuditConsumer",
    "KafkaAuditPublisher",
    "resolve_consumer_group",
    "scrub",
]
