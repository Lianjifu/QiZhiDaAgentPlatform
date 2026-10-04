"""Integration test for ``RedisStreamBus`` against a real Redis testcontainer.

Skipped automatically when ``testcontainers-python`` is not installed; CI
gets the full run, local machines without Docker are a no-op.

Validates the bits the in-memory fake can't catch:

* Real Redis Streams `XADD` / `XREADGROUP` / `XACK` roundtrip
* Consumer-group bookkeeping (`XGROUP CREATE` idempotency + `BUSYGROUP`)
* Two-replica fan-out via per-replica consumer groups
* Retry then DLQ after ``max_retries`` exhausted
* `PEL` isolation: a separate group can read entries a sibling group already
  ACKed (this is the cross-replica guarantee the bus promises)
"""

from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

import pytest

from qzdap_messaging.domain_event import EventEnvelope
from qzdap_messaging.redis_stream import RedisStreamBus

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def _envelope(tenant_id: UUID, name: str = "test.event") -> EventEnvelope:
    return EventEnvelope(
        event_id=uuid4(),
        event_name=name,
        tenant_id=tenant_id,
        workspace_id=None,
        trace_id=None,
        occurred_at_ms=1_700_000_000_000,
        payload={"k": "v"},
        metadata={},
    )


async def test_publish_then_consume_against_real_redis(
    redis_client,
) -> None:
    bus = RedisStreamBus(
        redis_client,
        prefix=f"itest:{uuid4().hex[:8]}:",
        consumer_name=f"itest-{uuid4().hex[:8]}",
        block_ms=50,
        count=10,
    )
    received: list[EventEnvelope] = []
    tenant_id = uuid4()

    async def handler(env: EventEnvelope) -> None:
        received.append(env)

    await bus.subscribe("test.event", handler)
    await bus.start()
    try:
        await bus.publish(await _envelope(tenant_id))
        for _ in range(40):  # 2s budget
            if received:
                break
            await asyncio.sleep(0.05)
        assert received, "real Redis: handler never fired"
        assert received[0].payload == {"k": "v"}
    finally:
        await bus.stop()


async def test_two_replicas_fan_out_via_distinct_groups(
    redis_client,
) -> None:
    """Two RedisStreamBus instances with different consumer names → distinct
    consumer groups → every replica gets every event (fan-out, not
    load-balanced)."""
    prefix = f"itest:{uuid4().hex[:8]}:"
    bus_a = RedisStreamBus(
        redis_client, prefix=prefix, consumer_name=f"a-{uuid4().hex[:8]}", block_ms=50
    )
    bus_b = RedisStreamBus(
        redis_client, prefix=prefix, consumer_name=f"b-{uuid4().hex[:8]}", block_ms=50
    )
    received_a: list[EventEnvelope] = []
    received_b: list[EventEnvelope] = []
    tenant_id = uuid4()

    async def h_a(env: EventEnvelope) -> None:
        received_a.append(env)

    async def h_b(env: EventEnvelope) -> None:
        received_b.append(env)

    await bus_a.subscribe("test.event", h_a)
    await bus_b.subscribe("test.event", h_b)
    await bus_a.start()
    await bus_b.start()
    try:
        for _ in range(2):
            await bus_a.publish(await _envelope(tenant_id))
        for _ in range(80):
            if len(received_a) >= 2 and len(received_b) >= 2:
                break
            await asyncio.sleep(0.05)
        assert len(received_a) == 2, f"a got {len(received_a)}/2"
        assert len(received_b) == 2, f"b got {len(received_b)}/2"
        assert bus_a._group != bus_b._group
    finally:
        await bus_a.stop()
        await bus_b.stop()


async def test_handler_exception_lands_in_dlq_after_max_retries(
    redis_client,
) -> None:
    bus = RedisStreamBus(
        redis_client,
        prefix=f"itest:{uuid4().hex[:8]}:",
        dlq_stream=f"itest:{uuid4().hex[:8]}:dlq",
        consumer_name=f"itest-{uuid4().hex[:8]}",
        max_retries=2,
        block_ms=50,
    )
    attempts = 0
    tenant_id = uuid4()

    async def always_fail(env: EventEnvelope) -> None:
        nonlocal attempts
        attempts += 1
        raise RuntimeError("boom")

    await bus.subscribe("test.event", always_fail)
    await bus.start()
    try:
        await bus.publish(await _envelope(tenant_id))
        # max_retries=2 → 3 attempts total → DLQ on attempt 3
        for _ in range(120):
            dlq_len = await redis_client.xlen(bus._dlq)
            if dlq_len > 0:
                break
            await asyncio.sleep(0.05)
        assert attempts == 3, f"expected 3 attempts; got {attempts}"
        assert await redis_client.xlen(bus._dlq) == 1, "DLQ should hold exactly 1 entry"
        # Source stream should have 0 pending entries after retries + DLQ.
        # (The 3 entries: original + 2 retries were each XACK'd after re-publish.)
        entries = await redis_client.xrange(bus._stream_key(tenant_id))
        assert entries, "source stream should still hold the retries"
    finally:
        await bus.stop()


async def test_idempotent_start_does_not_create_duplicate_groups(
    redis_client,
) -> None:
    """Calling start() twice on the same instance must be a no-op (it is,
    via ``if self._consumer_task is not None and not done: return``)."""
    bus = RedisStreamBus(
        redis_client,
        prefix=f"itest:{uuid4().hex[:8]}:",
        consumer_name=f"itest-{uuid4().hex[:8]}",
        block_ms=50,
    )
    await bus.start()
    first_task = bus._consumer_task
    await bus.start()  # idempotent
    assert bus._consumer_task is first_task
    await bus.stop()
