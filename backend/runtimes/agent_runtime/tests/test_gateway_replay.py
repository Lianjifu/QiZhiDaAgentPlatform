"""Gateway 的无感重放 —— 端口、摘要与门面编排。

依据：``docs/architecture/session-lifecycle.md``
（重复时返回什么）、§10 Stage 4b（启用无感重放）。

**这一层没有 DB、没有框架** —— 只验契约：读什么、怎么读、怎么证明重放与原流
一致。
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from qzdap_agent_runtime.gateway.facade import Gateway
from qzdap_agent_runtime.gateway.idempotency import IdempotencyGuard
from qzdap_agent_runtime.gateway.replay import (
    StoredEvent,
    event_digest,
    event_from_chunk,
)
from qzdap_agent_runtime.gateway.types import ChannelType
from qzdap_agent_runtime.gateway.web import WebChatNormalizer, WebIdentityVerifier
from qzdap_schema.dtos.turn import MessageChunk


class _Store:
    """事件存储的测试替身 —— 语义对齐 Session 侧的实现。"""

    def __init__(self, events: list[StoredEvent], status: str | None = "succeeded"):
        self._events = events
        self._status = status
        self.calls: list[tuple[UUID, UUID, int]] = []

    async def get_events(
        self, turn_id: UUID, *, tenant_id: UUID, after_seq: int = 0
    ) -> list[StoredEvent]:
        self.calls.append((turn_id, tenant_id, after_seq))
        return [event for event in self._events if event.seq > after_seq]

    async def get_turn_status(self, turn_id: UUID, *, tenant_id: UUID) -> str | None:
        return self._status


def _gateway(store=None) -> Gateway:  # type: ignore[no-untyped-def]
    class _Store:
        async def claim(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            raise AssertionError("重放路径不碰幂等守卫")

        async def record_weak(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            raise AssertionError("重放路径不碰幂等守卫")

        async def mark_completed(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            raise AssertionError("重放路径不碰幂等守卫")

        async def release(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            raise AssertionError("重放路径不碰幂等守卫")

    return Gateway(
        channels=None,
        identity=WebIdentityVerifier(),
        normalizers={ChannelType.WEB: WebChatNormalizer()},
        idempotency=IdempotencyGuard(_Store()),  # type: ignore[arg-type]
        events=store,
    )


def _chunk(seq: int, content: str) -> MessageChunk:
    return MessageChunk(turn_id=uuid4(), seq=seq, content=content)


# ── 摘要 ────────────────────────────────────────────────────────────────


def test_the_digest_covers_the_sequence_and_the_payload() -> None:
    events = [
        event_from_chunk(_chunk(1, "a")),
        event_from_chunk(_chunk(2, "b")),
    ]
    assert event_digest(events) == event_digest(list(events))
    assert event_digest(events) != event_digest(events[:1])


def test_the_digest_does_not_depend_on_the_key_order() -> None:
    """⚠️ JSONB **不保序** —— 摘要必须与键序无关，否则重放流永远对不上。"""
    first = StoredEvent(seq=1, event_type="message", payload={"a": 1, "b": 2})
    second = StoredEvent(seq=1, event_type="message", payload={"b": 2, "a": 1})
    assert event_digest([first]) == event_digest([second])


def test_an_event_is_built_from_the_chunk_itself() -> None:
    chunk = _chunk(3, "hello")
    event = event_from_chunk(chunk)
    assert event.seq == 3
    assert event.event_type == "message"
    assert event.payload["content"] == "hello"
    assert event.payload["seq"] == 3


# ── 门面 ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_the_replay_reads_the_events_after_the_given_seq() -> None:
    turn_id = uuid4()
    tenant_id = uuid4()
    store = _Store(
        [
            event_from_chunk(_chunk(1, "a")),
            event_from_chunk(_chunk(2, "b")),
            event_from_chunk(_chunk(3, "c")),
        ]
    )
    result = await _gateway(store).replay(turn_id, tenant_id=tenant_id, after_seq=1)
    assert [event.seq for event in result.events] == [2, 3]
    assert store.calls == [(turn_id, tenant_id, 1)]
    assert result.turn_id == turn_id
    assert result.is_finished is True


@pytest.mark.asyncio
async def test_a_turn_that_is_still_running_is_not_finished() -> None:
    result = await _gateway(_Store([], status="running")).replay(uuid4(), tenant_id=uuid4())
    assert result.events == []
    assert result.is_finished is False


@pytest.mark.asyncio
async def test_without_an_event_store_there_is_nothing_to_replay() -> None:
    """没有装配事件存储 → 空结果（调用方据此降级，不静默丢弃）。"""
    result = await _gateway(None).replay(uuid4(), tenant_id=uuid4())
    assert result.events == []
    assert result.status is None
    assert result.is_finished is False
