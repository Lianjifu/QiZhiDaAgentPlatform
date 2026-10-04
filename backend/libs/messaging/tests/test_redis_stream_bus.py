"""Unit tests for RedisStreamBus.

Two layers:

1. ``_resolve_consumer_name`` — env → hostname → uuid4 fallback chain
   (no Redis required).
2. ``RedisStreamBus`` — uses an in-memory fake redis client so the
   consumer loop, retry, and DLQ paths can be exercised without
   network / testcontainers.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

import pytest

from qzdap_messaging.domain_event import EventEnvelope
from qzdap_messaging.redis_stream import RedisStreamBus, _resolve_consumer_name

# ── _resolve_consumer_name ──────────────────────────────────────────────


def test_resolve_consumer_name_explicit_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("QZDAP_EVENT_REDIS_CONSUMER_NAME", raising=False)
    assert _resolve_consumer_name("explicit-name") == "explicit-name"


def test_resolve_consumer_name_env_wins_over_hostname(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("QZDAP_EVENT_REDIS_CONSUMER_NAME", "from-env")
    assert _resolve_consumer_name("") == "from-env"


def test_resolve_consumer_name_falls_back_to_uuid_when_hostname_blank(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("QZDAP_EVENT_REDIS_CONSUMER_NAME", raising=False)
    import socket

    monkeypatch.setattr(socket, "gethostname", lambda: "")
    name = _resolve_consumer_name("")
    assert name.startswith("host-")
    assert len(name) == len("host-") + 8


# ── Fake redis client ──────────────────────────────────────────────────


@dataclass
class _FakeStream:
    entries: list[tuple[str, dict[bytes, bytes]]] = field(default_factory=list)
    groups: set[str] = field(default_factory=set)
    # PEL[group][consumer] -> set of msg_ids delivered to this consumer
    # but not yet XACK'd. Mimics Redis Streams' at-least-once delivery
    # so the consumer doesn't re-deliver the same entry forever.
    pel: dict[str, dict[str, set[str]]] = field(default_factory=dict)


class _FakeRedis:
    """Minimal in-memory stand-in for ``redis.asyncio.Redis``.

    Implements just the surface ``RedisStreamBus`` touches: ``xadd``,
    ``xreadgroup`` (with PEL bookkeeping so entries are not re-delivered
    after ACK), ``xack``, ``xgroup_create``, ``keys``.
    """

    def __init__(self) -> None:
        self.streams: dict[bytes, _FakeStream] = {}
        self.xadd_calls: list[tuple[bytes, dict[bytes, bytes]]] = []
        self.xack_calls: list[tuple[bytes, str, str]] = []

    async def keys(self, pattern: str) -> list[bytes]:
        prefix = pattern.rstrip("*").encode()
        return [k for k in self.streams if k.startswith(prefix)]

    async def xgroup_create(
        self,
        key: bytes,
        group: str,
        id: str = "$",
        mkstream: bool = False,
    ) -> Any:
        stream = self.streams.setdefault(key, _FakeStream())
        if group in stream.groups:
            raise RuntimeError(f"BUSYGROUP Consumer Group name already exists {key!r}")
        stream.groups.add(group)
        return b"OK"

    async def xadd(
        self,
        key: bytes | str,
        fields: dict[bytes, bytes] | dict[str, str],
    ) -> str:
        if isinstance(key, str):
            key = key.encode()
        normalized: dict[bytes, bytes] = {}
        for k, v in fields.items():
            kk = k.encode() if isinstance(k, str) else k
            vv = v.encode() if isinstance(v, str) else v
            normalized[kk] = vv
        stream = self.streams.setdefault(key, _FakeStream())
        msg_id = f"{len(stream.entries) + 1}-0"
        stream.entries.append((msg_id, normalized))
        self.xadd_calls.append((key, normalized))
        return msg_id

    async def xreadgroup(
        self,
        groupname: str,
        consumername: str,
        streams: dict[bytes | str, str],
        count: int = 10,
        block: int = 0,
    ) -> list[tuple[bytes, list[tuple[bytes, dict[bytes, bytes]]]]]:
        out: list[tuple[bytes, list[tuple[bytes, dict[bytes, bytes]]]]] = []
        for k, last_id in streams.items():
            if isinstance(k, str):
                k = k.encode()
            stream = self.streams.get(k)
            if stream is None or groupname not in stream.groups:
                continue
            if last_id != ">":
                # Specific-ID replay — not exercised by these tests.
                continue
            # PEL bookkeeping: only deliver entries no consumer has yet
            # been handed (and not yet ACK'd).
            pending_in_group: set[str] = set()
            for consumer_pel in stream.pel.get(groupname, {}).values():
                pending_in_group.update(consumer_pel)
            new_entries: list[tuple[str, dict[bytes, bytes]]] = [
                (mid, fields)
                for mid, fields in stream.entries
                if mid not in pending_in_group
            ]
            chunk = new_entries[:count]
            if chunk:
                # Mark these as delivered to *this* consumer
                stream.pel.setdefault(groupname, {}).setdefault(
                    consumername, set()
                ).update(mid for mid, _ in chunk)
                # xreadgroup returns msg_id as bytes in real Redis
                out.append((k, [(mid.encode(), fields) for mid, fields in chunk]))
        return out

    async def xack(self, key: bytes | str, group: str, msg_id: str) -> int:
        if isinstance(key, str):
            key = key.encode()
        self.xack_calls.append((key, group, msg_id))
        stream = self.streams.get(key)
        if stream and group in stream.pel:
            for consumer_pel in stream.pel[group].values():
                consumer_pel.discard(msg_id)
        return 1


def _envelope(tenant_id: UUID | None = None, name: str = "test.event") -> EventEnvelope:
    return EventEnvelope(
        event_id=uuid4(),
        event_name=name,
        tenant_id=tenant_id or UUID("00000000-0000-0000-0000-000000000001"),
        workspace_id=None,
        trace_id=None,
        occurred_at_ms=1_700_000_000_000,
        payload={"k": "v"},
        metadata={},
    )


# ── publish / subscribe round-trip ─────────────────────────────────────


@pytest.mark.asyncio
async def test_publish_then_consumer_dispatches_to_subscribers() -> None:
    fake = _FakeRedis()
    bus = RedisStreamBus(fake, block_ms=10, count=10)  # type: ignore[arg-type]
    received: list[EventEnvelope] = []

    async def handler(env: EventEnvelope) -> None:
        received.append(env)

    await bus.subscribe("test.event", handler)
    await bus.start()
    try:
        env = _envelope()
        await bus.publish(env)
        # wait for consumer to pick it up
        for _ in range(50):
            if received:
                break
            await asyncio.sleep(0.05)
        assert received, "consumer never received the published event"
        assert received[0].event_name == env.event_name
        assert received[0].payload == env.payload
    finally:
        await bus.stop()


@pytest.mark.asyncio
async def test_publish_acks_when_no_subscribers() -> None:
    fake = _FakeRedis()
    bus = RedisStreamBus(fake, block_ms=10, count=10)  # type: ignore[arg-type]
    await bus.start()
    try:
        env = _envelope()
        await bus.publish(env)
        # wait for consumer to pick it up + ACK
        for _ in range(50):
            if fake.xack_calls:
                break
            await asyncio.sleep(0.05)
        assert fake.xack_calls, "consumer never acked the unhandled event"
    finally:
        await bus.stop()


# ── DLQ + retry ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_handler_exception_retries_then_dlqs() -> None:
    fake = _FakeRedis()
    bus = RedisStreamBus(fake, block_ms=10, count=10, max_retries=2)  # type: ignore[arg-type]

    async def always_fail(env: EventEnvelope) -> None:
        raise RuntimeError("boom")

    await bus.subscribe("test.event", always_fail)
    await bus.start()
    try:
        env = _envelope()
        await bus.publish(env)
        # wait until DLQ has 1 entry — i.e., max_retries exhausted
        dlq_key = b"qzdap:events:dlq"
        for _ in range(100):
            if fake.streams.get(dlq_key):
                break
            await asyncio.sleep(0.05)
        dlq = fake.streams[dlq_key]
        assert len(dlq.entries) == 1, (
            f"expected DLQ to receive one entry; got {len(dlq.entries)}"
        )
        _, fields = dlq.entries[0]
        assert fields[b"dlq_reason"] == b"max_retries_exceeded"
        # retry_count must exceed max_retries (3 attempts: 0 → 1 → 2 → DLQ at next_count=3)
        assert int(fields[b"retry_count"]) > 2
        # Source stream should be empty after retries finished
        src = fake.streams[b"qzdap:events:00000000-0000-0000-0000-000000000001"]
        assert all(int(f.get(b"retry_count", b"0")) <= 2 for _, f in src.entries), (
            "retry_count must not exceed max_retries in source stream"
        )
    finally:
        await bus.stop()


@pytest.mark.asyncio
async def test_handler_eventually_succeeds_within_retry_budget() -> None:
    fake = _FakeRedis()
    bus = RedisStreamBus(fake, block_ms=10, count=10, max_retries=3)  # type: ignore[arg-type]
    attempts: list[int] = []

    async def flaky(env: EventEnvelope) -> None:
        attempts.append(1)
        if len(attempts) < 2:
            raise RuntimeError("transient")

    await bus.subscribe("test.event", flaky)
    await bus.start()
    try:
        await bus.publish(_envelope())
        for _ in range(100):
            if fake.xack_calls:
                break
            await asyncio.sleep(0.05)
        assert len(attempts) == 2, (
            f"expected 2 attempts (1 fail + 1 success); got {len(attempts)}"
        )
        assert fake.xack_calls, "should have ACK'd the eventually-successful event"
        # No DLQ
        assert (
            b"qzdap:events:dlq" not in fake.streams
            or not fake.streams[b"qzdap:events:dlq"].entries
        )
    finally:
        await bus.stop()


# ── Cross-replica consumer name isolation ───────────────────────────────


@pytest.mark.asyncio
async def test_two_buses_with_distinct_names_fan_out() -> None:
    """Two replicas with distinct consumer names live in distinct consumer
    groups → every replica gets every event (fan-out, not load-balanced).
    """
    fake = _FakeRedis()
    bus_a = RedisStreamBus(fake, consumer_name="replica-a", block_ms=10)  # type: ignore[arg-type]
    bus_b = RedisStreamBus(fake, consumer_name="replica-b", block_ms=10)  # type: ignore[arg-type]
    received_a: list[EventEnvelope] = []
    received_b: list[EventEnvelope] = []

    async def handler_a(env: EventEnvelope) -> None:
        received_a.append(env)

    async def handler_b(env: EventEnvelope) -> None:
        received_b.append(env)

    await bus_a.subscribe("test.event", handler_a)
    await bus_b.subscribe("test.event", handler_b)
    await bus_a.start()
    await bus_b.start()
    try:
        for _ in range(2):
            await bus_a.publish(_envelope())
        for _ in range(100):
            if len(received_a) >= 2 and len(received_b) >= 2:
                break
            await asyncio.sleep(0.05)
        assert len(received_a) == 2, (
            f"replica-a should see all 2 events; got {len(received_a)}"
        )
        assert len(received_b) == 2, (
            f"replica-b should see all 2 events; got {len(received_b)}"
        )
        # Distinct consumer groups → no cross-PEL interference.
        assert bus_a._group != bus_b._group  # type: ignore[attr-defined]
    finally:
        await bus_a.stop()
        await bus_b.stop()


# ── Consumer name resolution ────────────────────────────────────────────


def test_consumer_name_property_reflects_resolved_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("QZDAP_EVENT_REDIS_CONSUMER_NAME", raising=False)
    fake = _FakeRedis()
    bus = RedisStreamBus(fake, consumer_name="")  # type: ignore[arg-type]
    assert bus.consumer_name != ""
    # explicit name wins
    bus2 = RedisStreamBus(fake, consumer_name="explicit")  # type: ignore[arg-type]
    assert bus2.consumer_name == "explicit"


# ── Start idempotency ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_start_is_idempotent() -> None:
    fake = _FakeRedis()
    bus = RedisStreamBus(fake, block_ms=10)  # type: ignore[arg-type]
    await bus.start()
    task1 = bus._consumer_task  # type: ignore[attr-defined]
    await bus.start()  # second call must be a no-op
    task2 = bus._consumer_task  # type: ignore[attr-defined]
    assert task1 is task2
    await bus.stop()


@pytest.mark.asyncio
async def test_stop_then_restart_replaces_task() -> None:
    fake = _FakeRedis()
    bus = RedisStreamBus(fake, block_ms=10)  # type: ignore[arg-type]
    await bus.start()
    task1 = bus._consumer_task  # type: ignore[attr-defined]
    await bus.stop()
    assert bus._consumer_task is None  # type: ignore[attr-defined]
    await bus.start()
    task2 = bus._consumer_task  # type: ignore[attr-defined]
    assert task1 is not task2
    await bus.stop()
