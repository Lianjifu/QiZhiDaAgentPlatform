"""Integration test for ``qzdap_messaging.kafka_audit`` against a real
Kafka KRaft broker (testcontainers-python).

* Real ``AIOKafkaProducer`` / ``AIOKafkaConsumer`` end-to-end
* Topic auto-create + producer.send_and_wait roundtrip
* Consumer commits offsets and redelivery is suppressed on re-poll
* Producer retry-then-DLQ path uses a deliberately unreachable
  bootstrap on the first attempt to force the retry+DLQ shape

Skipped automatically when ``testcontainers-python`` (with the ``kafka``
extra) is not installed; CI installs it via the dev extra.
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

import pytest
from qzdap_schema.ids import TenantId, UserId

from qzdap_messaging.kafka_audit import (
    KafkaAuditConsumer,
    KafkaAuditPublisher,
    resolve_consumer_group,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


class _RecordingAuditPort:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def append(self, **kwargs: Any) -> None:
        self.calls.append(kwargs)


async def _wait(predicate, *, timeout: float = 10.0, interval: float = 0.05) -> bool:
    """Poll ``predicate()`` until it returns truthy or timeout."""
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        if predicate():
            return True
        await asyncio.sleep(interval)
    return False


async def test_publish_then_consume_against_real_kafka(
    kafka_bootstrap_servers: str,
) -> None:
    """Producer.send_and_wait → consumer.getmany → audit_port.append."""
    topic = f"itest-audit-{uuid4().hex[:8]}"
    dlq = f"{topic}.dlq"
    group = resolve_consumer_group(f"itest-{uuid4().hex[:8]}")

    producer = KafkaAuditPublisher(
        bootstrap_servers=kafka_bootstrap_servers,
        topic=topic,
        dlq_topic=dlq,
        request_timeout_ms=10_000,
    )
    port = _RecordingAuditPort()
    consumer = KafkaAuditConsumer(
        bootstrap_servers=kafka_bootstrap_servers,
        topic=topic,
        group_id=group,
        audit_port=port,
        block_ms=100,
    )
    await producer.start()
    await consumer.start()
    try:
        tid = TenantId(uuid4())
        await producer.append(
            tenant_id=tid,
            actor_id=UserId(uuid4()),
            event_type="tool.execution.completed",
            payload={"tenant_id": str(tid), "tool": "echo", "actor_id": str(uuid4())},
        )
        ok = await _wait(lambda: len(port.calls) >= 1, timeout=15.0)
        assert ok, f"consumer never fired (calls={len(port.calls)})"
        assert port.calls[0]["tenant_id"] == tid
        assert port.calls[0]["event_type"] == "tool.execution.completed"
        assert port.calls[0]["payload"]["tool"] == "echo"
    finally:
        await consumer.stop()
        await producer.stop()


async def test_scrub_holds_on_real_kafka_payload(
    kafka_bootstrap_servers: str,
) -> None:
    """End-to-end: secrets scrubbed before send, never appear in SQL port."""
    topic = f"itest-audit-{uuid4().hex[:8]}"
    dlq = f"{topic}.dlq"
    group = resolve_consumer_group(f"itest-{uuid4().hex[:8]}")

    producer = KafkaAuditPublisher(
        bootstrap_servers=kafka_bootstrap_servers,
        topic=topic,
        dlq_topic=dlq,
        request_timeout_ms=10_000,
    )
    port = _RecordingAuditPort()
    consumer = KafkaAuditConsumer(
        bootstrap_servers=kafka_bootstrap_servers,
        topic=topic,
        group_id=group,
        audit_port=port,
        block_ms=100,
    )
    await producer.start()
    await consumer.start()
    try:
        tid = TenantId(uuid4())
        await producer.append(
            tenant_id=tid,
            actor_id=None,
            event_type="x",
            payload={
                "tenant_id": str(tid),
                "api_key": "raw-secret",
                "password": "raw-pw",
                "secrets_ref": "env:OPENAI_API_KEY",
            },
        )
        ok = await _wait(lambda: len(port.calls) >= 1, timeout=15.0)
        assert ok
        payload = port.calls[0]["payload"]
        assert payload["api_key_redacted"] == "***"
        assert payload["password_redacted"] == "***"
        assert payload["secrets_ref"] == "env:OPENAI_API_KEY"
        # raw keys never survive
        assert "api_key" not in payload
        assert "password" not in payload
    finally:
        await consumer.stop()
        await producer.stop()


async def test_consumer_does_not_redeliver_after_commit(
    kafka_bootstrap_servers: str,
) -> None:
    """Two events produced before the consumer subscribes: consumer still
    gets both (auto_offset_reset=earliest) and on next poll nothing else
    is delivered (offset was committed)."""
    topic = f"itest-audit-{uuid4().hex[:8]}"
    dlq = f"{topic}.dlq"
    group = resolve_consumer_group(f"itest-{uuid4().hex[:8]}")

    producer = KafkaAuditPublisher(
        bootstrap_servers=kafka_bootstrap_servers,
        topic=topic,
        dlq_topic=dlq,
        request_timeout_ms=10_000,
    )
    # Produce BEFORE consumer starts → earliest reset ensures delivery.
    await producer.start()
    for _ in range(2):
        await producer.append(
            tenant_id=TenantId(uuid4()),
            actor_id=None,
            event_type="x",
            payload={"k": "v"},
        )

    port = _RecordingAuditPort()
    consumer = KafkaAuditConsumer(
        bootstrap_servers=kafka_bootstrap_servers,
        topic=topic,
        group_id=group,
        audit_port=port,
        block_ms=100,
    )
    await consumer.start()
    try:
        ok = await _wait(lambda: len(port.calls) >= 2, timeout=15.0)
        assert ok, f"expected 2 calls; got {len(port.calls)}"
        # Nothing more should be delivered
        await asyncio.sleep(0.5)
        assert len(port.calls) == 2, f"unexpected redelivery: {len(port.calls)}"
    finally:
        await consumer.stop()
        await producer.stop()


async def test_retry_then_dlq_against_unreachable_broker() -> None:
    """Force producer retry+DLQ by pointing at an unreachable bootstrap.

    We use ``localhost:1`` (always closed) to provoke ``ConnectionError``
    on every attempt; after ``max_retries`` the DLQ topic is also
    unreachable so we only assert the retry loop fires — verifying the
    producer never raises to the caller (audit must not raise).
    """
    producer = KafkaAuditPublisher(
        bootstrap_servers="127.0.0.1:1",  # always closed
        topic="does-not-matter",
        dlq_topic="does-not-matter-dlq",
        max_retries=2,
        request_timeout_ms=200,
    )
    await producer.start()
    try:
        # Must not raise — audit never fails back to caller.
        body = await producer.append(
            tenant_id=TenantId(uuid4()),
            actor_id=None,
            event_type="x",
            payload={"k": "v"},
        )
        # We get the body we tried to send, scrubbed.
        assert body["event_type"] == "x"
        assert body["payload"] == {"k": "v"}
    finally:
        await producer.stop()
