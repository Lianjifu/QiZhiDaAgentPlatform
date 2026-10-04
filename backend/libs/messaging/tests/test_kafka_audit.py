"""Unit tests for ``qzdap_messaging.kafka_audit``.

No broker required: ``AIOKafkaProducer`` / ``AIOKafkaConsumer`` are
replaced with ``_FakeAIOKafkaProducer`` / ``_FakeAIOKafkaConsumer`` via
monkeypatch. Mirrors the ``_FakeRedis`` pattern used in
``test_redis_stream_bus.py``.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any
from uuid import uuid4

import pytest
from qzdap_schema.ids import TenantId, UserId

from qzdap_messaging import kafka_audit
from qzdap_messaging.kafka_audit import (
    KafkaAuditConsumer,
    KafkaAuditPublisher,
    resolve_consumer_group,
    scrub,
)

# asyncio_mode = "auto" in pyproject.toml → async tests auto-marked.
# Sync tests in this file live alongside async ones without a module-level
# pytestmark so pytest-asyncio doesn't warn about non-async callables.


# ── fakes ──────────────────────────────────────────────────────────────────


class _FakePartition:
    def __init__(self, topic: str, partition: int = 0) -> None:
        self.topic = topic
        self.partition = partition

    def __hash__(self) -> int:
        return hash((self.topic, self.partition))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, _FakePartition):
            return NotImplemented
        return self.topic == other.topic and self.partition == other.partition


class _FakeRecord:
    __slots__ = ("key", "offset", "value")

    def __init__(self, value: dict[str, Any], key: str | None, offset: int) -> None:
        self.value = value
        self.key = key
        self.offset = offset


class _FakeAIOKafkaProducer:
    """In-memory stand-in for ``AIOKafkaProducer``."""

    def __init__(self, *, bootstrap_servers: str, **_: Any) -> None:
        self.bootstrap_servers = bootstrap_servers
        self.started = False
        self.stopped = False
        self._sent: list[tuple[str, dict[str, Any], str | None]] = []
        self._fail_n_times: dict[str, int] = {}
        self._default_fail_n = 0

    def fail_next_n(self, topic: str, n: int) -> None:
        self._fail_n_times[topic] = n

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.stopped = True

    async def send_and_wait(self, topic: str, *, value: Any, key: Any) -> None:
        remain = self._fail_n_times.get(topic, 0)
        if remain > 0:
            self._fail_n_times[topic] = remain - 1
            self._default_fail_n = max(0, self._default_fail_n - 1)
            raise ConnectionError(f"fake broker reject (remaining={remain - 1})")
        self._sent.append((topic, value, key))


class _FakeAIOKafkaConsumer:
    """In-memory stand-in for ``AIOKafkaConsumer``.

    Stores messages in a per-topic list and exposes ``getmany`` matching
    aiokafka's shape: ``dict[TopicPartition, list[ConsumerRecord]]``.
    """

    def __init__(
        self, topic: str, *, bootstrap_servers: str, group_id: str, **_: Any
    ) -> None:
        self.topic = topic
        self.bootstrap_servers = bootstrap_servers
        self.group_id = group_id
        self.started = False
        self.stopped = False
        self._messages: list[dict[str, Any]] = []
        self._committed: list[Any] = []
        self._cursor = 0
        self._offset = 0
        # Per-call ``getmany`` returns whatever was queued since last call.
        self._pending: list[dict[str, Any]] = []

    def enqueue(self, value: dict[str, Any], key: str | None) -> None:
        self._pending.append({"value": value, "key": key})

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.stopped = True

    async def getmany(
        self, *, timeout_ms: int, max_records: int
    ) -> dict[_FakePartition, list[_FakeRecord]]:
        # Real aiokafka returns {} immediately when no records + non-blocking.
        if not self._pending:
            return {}
        tp = _FakePartition(self.topic)
        out: list[_FakeRecord] = []
        for i in range(min(max_records, len(self._pending))):
            msg = self._pending.pop(0)
            offset = self._offset
            self._offset += 1
            out.append(_FakeRecord(value=msg["value"], key=msg["key"], offset=offset))
        return {tp: out}

    async def commit(self, offsets: dict[_FakePartition, int]) -> None:
        self._committed.append(dict(offsets))


@pytest.fixture
def fake_producer(monkeypatch: pytest.MonkeyPatch):
    holder: dict[str, _FakeAIOKafkaProducer] = {}

    def factory(**kwargs: Any) -> _FakeAIOKafkaProducer:
        p = _FakeAIOKafkaProducer(**kwargs)
        holder["instance"] = p
        return p

    monkeypatch.setattr(kafka_audit, "AIOKafkaProducer", factory)
    return holder


@pytest.fixture
def fake_consumer(monkeypatch: pytest.MonkeyPatch):
    holder: dict[str, _FakeAIOKafkaConsumer] = {}

    def factory(topic: str, **kwargs: Any) -> _FakeAIOKafkaConsumer:
        c = _FakeAIOKafkaConsumer(topic, **kwargs)
        holder["instance"] = c
        return c

    monkeypatch.setattr(kafka_audit, "AIOKafkaConsumer", factory)
    return holder


# ── scrub ──────────────────────────────────────────────────────────────────


class TestScrub:
    def test_scrubs_known_sensitive_keys(self) -> None:
        out = scrub(
            {
                "tenant_id": "t1",
                "api_key": "raw",
                "password": "pw",
                "token": "tok",
                "secret": "shh",
                "authorization": "Bearer x",
                "secrets_ref": "env:OPENAI_API_KEY",
            }
        )
        assert out["api_key_redacted"] == "***"
        assert out["password_redacted"] == "***"
        assert out["token_redacted"] == "***"
        assert out["secret_redacted"] == "***"
        assert out["authorization_redacted"] == "***"
        assert out["secrets_ref"] == "env:OPENAI_API_KEY"
        assert out["tenant_id"] == "t1"
        # original keys must not survive
        assert "api_key" not in out
        assert "password" not in out
        assert "token" not in out
        assert "secret" not in out
        assert "authorization" not in out

    def test_case_insensitive(self) -> None:
        out = scrub({"API_KEY": "raw", "Password": "pw"})
        assert out["API_KEY_redacted"] == "***"
        assert out["Password_redacted"] == "***"

    def test_passes_through_non_sensitive(self) -> None:
        out = scrub({"tenant_id": "t1", "actor_id": "a", "event_type": "x"})
        assert out == {"tenant_id": "t1", "actor_id": "a", "event_type": "x"}


# ── producer ───────────────────────────────────────────────────────────────


class TestProducer:
    async def test_start_is_idempotent(
        self, fake_producer: dict[str, _FakeAIOKafkaProducer]
    ) -> None:
        pub = KafkaAuditPublisher(
            bootstrap_servers="fake:9092",
            topic="t",
            dlq_topic="t.dlq",
        )
        await pub.start()
        await pub.start()  # no-op
        assert pub.started
        assert fake_producer["instance"].started
        assert len(fake_producer) == 1  # only one producer created
        await pub.stop()

    async def test_append_before_start_raises(self) -> None:
        pub = KafkaAuditPublisher(
            bootstrap_servers="fake:9092", topic="t", dlq_topic="t.dlq"
        )
        with pytest.raises(RuntimeError, match="not started"):
            await pub.append(
                tenant_id=TenantId(uuid4()),
                actor_id=None,
                event_type="x",
                payload={"k": "v"},
            )

    async def test_append_sends_to_main_topic_with_tenant_key(
        self, fake_producer: dict[str, _FakeAIOKafkaProducer]
    ) -> None:
        pub = KafkaAuditPublisher(
            bootstrap_servers="fake:9092", topic="qzdap.audit.events", dlq_topic="dlq"
        )
        await pub.start()
        try:
            tid = TenantId(uuid4())
            aid = UserId(uuid4())
            body = await pub.append(
                tenant_id=tid,
                actor_id=aid,
                event_type="tool.execution.completed",
                payload={"tenant_id": str(tid), "actor_id": str(aid), "tool": "echo"},
            )
            assert body["tenant_id"] == str(tid)
            assert body["actor_id"] == str(aid)
            assert body["event_type"] == "tool.execution.completed"
            assert body["payload"]["tool"] == "echo"
            assert body["schema_version"] == 1
            # Verify sent
            sent = fake_producer["instance"]._sent
            assert len(sent) == 1
            topic, value, key = sent[0]
            assert topic == "qzdap.audit.events"
            assert key == str(tid)
            # Value should have been JSON-serialized then deserialized
            # by the fake serializer pair... we stored the dict directly.
            assert value == body
        finally:
            await pub.stop()

    async def test_append_scrubs_before_send(
        self, fake_producer: dict[str, _FakeAIOKafkaProducer]
    ) -> None:
        pub = KafkaAuditPublisher(
            bootstrap_servers="fake:9092", topic="t", dlq_topic="dlq"
        )
        await pub.start()
        try:
            await pub.append(
                tenant_id=TenantId(uuid4()),
                actor_id=None,
                event_type="x",
                payload={"api_key": "raw", "secrets_ref": "env:X"},
            )
            _, value, _ = fake_producer["instance"]._sent[0]
            assert value["payload"]["api_key_redacted"] == "***"
            assert value["payload"]["secrets_ref"] == "env:X"
        finally:
            await pub.stop()

    async def test_retry_then_succeed(
        self, fake_producer: dict[str, _FakeAIOKafkaProducer]
    ) -> None:
        pub = KafkaAuditPublisher(
            bootstrap_servers="fake:9092", topic="t", dlq_topic="dlq", max_retries=3
        )
        await pub.start()
        try:
            fake_producer["instance"].fail_next_n("t", 2)
            await pub.append(
                tenant_id=TenantId(uuid4()),
                actor_id=None,
                event_type="x",
                payload={"k": "v"},
            )
            # 2 fails + 1 success = 3 attempts, 1 successful send
            assert len(fake_producer["instance"]._sent) == 1
        finally:
            await pub.stop()

    async def test_retry_then_dlq(
        self, fake_producer: dict[str, _FakeAIOKafkaProducer]
    ) -> None:
        pub = KafkaAuditPublisher(
            bootstrap_servers="fake:9092", topic="t", dlq_topic="dlq", max_retries=2
        )
        await pub.start()
        try:
            # Fail 3 times (> max_retries=2) so DLQ fires
            fake_producer["instance"].fail_next_n("t", 3)
            await pub.append(
                tenant_id=TenantId(uuid4()),
                actor_id=None,
                event_type="x",
                payload={"k": "v"},
            )
            sent = fake_producer["instance"]._sent
            # Only the DLQ message was sent successfully
            assert len(sent) == 1
            topic, value, key = sent[0]
            assert topic == "dlq"
            assert "dlq_reason" in value
            assert key is not None
        finally:
            await pub.stop()

    async def test_stop_is_idempotent(
        self, fake_producer: dict[str, _FakeAIOKafkaProducer]
    ) -> None:
        pub = KafkaAuditPublisher(
            bootstrap_servers="fake:9092", topic="t", dlq_topic="dlq"
        )
        await pub.start()
        await pub.stop()
        await pub.stop()  # no-op
        assert not pub.started


# ── consumer ───────────────────────────────────────────────────────────────


class _RecordingAuditPort:
    """Captures ``append()`` calls for the consumer test."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self._fail = False

    def make_next_fail(self) -> None:
        self._fail = True

    async def append(self, **_kwargs: Any) -> None:
        self.calls.append(_kwargs)
        if self._fail:
            self._fail = False
            raise RuntimeError("audit sql down")


class TestConsumer:
    async def test_start_creates_task_and_consumer(
        self, fake_consumer: dict[str, _FakeAIOKafkaConsumer]
    ) -> None:
        port = _RecordingAuditPort()
        consumer = KafkaAuditConsumer(
            bootstrap_servers="fake:9092",
            topic="t",
            group_id="g",
            audit_port=port,
        )
        await consumer.start()
        try:
            assert consumer.task is not None
            assert not consumer.task.done()
            c = fake_consumer["instance"]
            assert c.started
            assert c.bootstrap_servers == "fake:9092"
            assert c.group_id == "g"
            assert c.topic == "t"
        finally:
            await consumer.stop()

    async def test_start_is_idempotent(
        self, fake_consumer: dict[str, _FakeAIOKafkaConsumer]
    ) -> None:
        port = _RecordingAuditPort()
        consumer = KafkaAuditConsumer(
            bootstrap_servers="fake:9092",
            topic="t",
            group_id="g",
            audit_port=port,
        )
        await consumer.start()
        first_task = consumer.task
        await consumer.start()  # no-op
        assert consumer.task is first_task
        await consumer.stop()

    async def test_stop_drains_and_cancels_task(
        self, fake_consumer: dict[str, _FakeAIOKafkaConsumer]
    ) -> None:
        port = _RecordingAuditPort()
        consumer = KafkaAuditConsumer(
            bootstrap_servers="fake:9092",
            topic="t",
            group_id="g",
            audit_port=port,
        )
        await consumer.start()
        task = consumer.task
        assert task is not None
        await consumer.stop()
        assert consumer.task is None
        assert task.done()
        assert fake_consumer["instance"].stopped

    async def test_dispatch_invokes_audit_port(
        self, fake_consumer: dict[str, _FakeAIOKafkaConsumer]
    ) -> None:
        port = _RecordingAuditPort()
        consumer = KafkaAuditConsumer(
            bootstrap_servers="fake:9092",
            topic="t",
            group_id="g",
            audit_port=port,
        )
        # Direct dispatch — bypass the loop for the unit assertion.
        tid = uuid4()
        await consumer._dispatch(
            {
                "tenant_id": str(tid),
                "actor_id": None,
                "event_type": "x",
                "payload": {"k": "v"},
            }
        )
        assert len(port.calls) == 1
        call = port.calls[0]
        assert call["tenant_id"] == TenantId(tid)
        assert call["actor_id"] is None
        assert call["event_type"] == "x"
        assert call["payload"] == {"k": "v"}

    async def test_dispatch_skips_bad_tenant_id(
        self, fake_consumer: dict[str, _FakeAIOKafkaConsumer]
    ) -> None:
        port = _RecordingAuditPort()
        consumer = KafkaAuditConsumer(
            bootstrap_servers="fake:9092",
            topic="t",
            group_id="g",
            audit_port=port,
        )
        await consumer._dispatch({"tenant_id": "not-a-uuid"})
        assert port.calls == []


# ── roundtrip ──────────────────────────────────────────────────────────────


class TestRoundtrip:
    async def test_producer_to_consumer_via_in_memory_bridge(
        self,
        fake_producer: dict[str, _FakeAIOKafkaProducer],
        fake_consumer: dict[str, _FakeAIOKafkaConsumer],
    ) -> None:
        """Producer publishes → consumer's fake pulls → audit_port.append called.

        We hand-deliver the producer's output to the consumer's fake
        enqueue queue (mimicking the broker), then run the loop one tick.
        """
        port = _RecordingAuditPort()
        producer = KafkaAuditPublisher(
            bootstrap_servers="fake:9092", topic="t", dlq_topic="dlq"
        )
        consumer = KafkaAuditConsumer(
            bootstrap_servers="fake:9092",
            topic="t",
            group_id="g",
            audit_port=port,
        )
        await producer.start()
        await consumer.start()
        try:
            tid = TenantId(uuid4())
            await producer.append(
                tenant_id=tid,
                actor_id=None,
                event_type="tool.execution.completed",
                payload={"tenant_id": str(tid), "tool": "echo"},
            )

            # Bridge: the fake producer's serializer would have turned the
            # dict into JSON bytes; replicate by re-encoding.
            _topic, value, key = fake_producer["instance"]._sent[0]
            # The fake serializer stored the dict directly; mimic real
            # broker by re-serializing through our serializer pair.
            wire_value = json.loads(json.dumps(value))
            wire_key = key
            fake_consumer["instance"].enqueue(wire_value, wire_key)

            # Give the consumer loop a couple of getmany ticks.
            for _ in range(5):
                if port.calls:
                    break
                await asyncio.sleep(0.05)

            assert len(port.calls) == 1
            assert port.calls[0]["tenant_id"] == tid
            assert port.calls[0]["event_type"] == "tool.execution.completed"
            assert port.calls[0]["payload"]["tool"] == "echo"
            # Offset was committed
            assert fake_consumer["instance"]._committed
        finally:
            await consumer.stop()
            await producer.stop()


# ── resolve_consumer_group ─────────────────────────────────────────────────


def test_resolve_consumer_group_explicit_wins() -> None:
    assert resolve_consumer_group("explicit-value") == "explicit-value"


def test_resolve_consumer_group_env_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("QZDAP_AUDIT_KAFKA_CONSUMER_GROUP", "env-value")
    assert resolve_consumer_group() == "env-value"


def test_resolve_consumer_group_hostname_fallback() -> None:
    # No env var set → hostname or uuid4.

    import os

    os.environ.pop("QZDAP_AUDIT_KAFKA_CONSUMER_GROUP", None)
    g = resolve_consumer_group()
    assert g.startswith("qzdap-audit-")


def test_resolve_consumer_group_explicit_overrides_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("QZDAP_AUDIT_KAFKA_CONSUMER_GROUP", "env-value")
    assert resolve_consumer_group("explicit") == "explicit"
