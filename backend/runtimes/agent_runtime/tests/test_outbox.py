"""Tests for outbox worker (§4.4)."""

from __future__ import annotations

import asyncio
import pytest

from qzdap_agent_runtime.outbox import (
    DispatchError,
    InMemoryOutboxRepository,
    MAX_DELIVERY_ATTEMPTS,
    OutboxDispatcher,
    OutboxEvent,
    OutboxRepository,
    OutboxWorker,
    compute_retry_delay,
)


# ---------------------------------------------------------------------------
# compute_retry_delay
# ---------------------------------------------------------------------------


class TestComputeRetryDelay:
    def test_first_attempt_near_base(self) -> None:
        """attempt=1 时, 基础值 1s (±20% jitter)。"""
        for _ in range(50):
            delay = compute_retry_delay(1)
            assert 0.8 <= delay <= 1.2

    def test_growth(self) -> None:
        """每次 attempt 翻倍 (直到上限)。"""
        # attempt=1: ~1s ±20%, attempt=2: ~2s ±20%, attempt=3: ~4s ±20%
        for _ in range(50):
            d1 = compute_retry_delay(1)
            d2 = compute_retry_delay(2)
            d3 = compute_retry_delay(3)
        # ±20% 区间
        assert 0.8 <= d1 <= 1.2
        assert 1.6 <= d2 <= 2.4
        assert 3.2 <= d3 <= 4.8

    def test_cap_at_max(self) -> None:
        """attempt 足够大时, 必须封顶在 RETRY_MAX_SECONDS=300s。"""
        for attempt in (10, 20, 100):
            delay = compute_retry_delay(attempt)
            assert delay <= 300.0

    def test_attempt_zero_falls_back_to_one(self) -> None:
        """attempt=0 (非法) 必须 fallback 到 attempt=1。"""
        assert 0.5 < compute_retry_delay(0) < 1.5


# ---------------------------------------------------------------------------
# InMemoryOutboxRepository
# ---------------------------------------------------------------------------


def _make_event(
    turn_id: str = "t-1",
    seq: int = 1,
    status: str = "pending",
    attempts: int = 0,
) -> OutboxEvent:
    return OutboxEvent(
        turn_id=turn_id,
        seq=seq,
        event_type="message",
        payload={"content": "hi"},
        delivery_status=status,
        delivery_attempts=attempts,
    )


class TestInMemoryOutboxRepository:
    def test_list_pending_returns_ordered(self) -> None:
        repo = InMemoryOutboxRepository()
        repo.add(_make_event(turn_id="t-1", seq=2))
        repo.add(_make_event(turn_id="t-1", seq=1))
        repo.add(_make_event(turn_id="t-2", seq=1))

        events = asyncio.run(repo.list_pending(limit=10))
        # 必须按 (turn_id, seq) 升序
        assert [(e.turn_id, e.seq) for e in events] == [
            ("t-1", 1), ("t-1", 2), ("t-2", 1),
        ]

    def test_list_pending_excludes_delivered(self) -> None:
        repo = InMemoryOutboxRepository()
        repo.add(_make_event(seq=1, status="pending"))
        repo.add(_make_event(seq=2, status="delivered"))
        events = asyncio.run(repo.list_pending(limit=10))
        assert len(events) == 1
        assert events[0].seq == 1

    def test_list_pending_exceeds_max_attempts(self) -> None:
        """attempts 达到上限的事件必须被 list_pending 排除(只入死信不再重试)。"""
        repo = InMemoryOutboxRepository()
        repo.add(_make_event(seq=1, status="failed", attempts=MAX_DELIVERY_ATTEMPTS))
        events = asyncio.run(repo.list_pending(limit=10))
        assert events == []

    async def test_mark_delivered(self) -> None:
        repo = InMemoryOutboxRepository()
        repo.add(_make_event(seq=1))
        await repo.mark_delivered("t-1", 1)
        events = await repo.list_pending(limit=10)
        assert events == []  # 已投递,不再 pending

    async def test_mark_failed_increments_attempts(self) -> None:
        repo = InMemoryOutboxRepository()
        repo.add(_make_event(seq=1, status="pending", attempts=0))
        await repo.mark_failed("t-1", 1, attempts=1, last_error="boom")
        events = await repo.list_pending(limit=10)
        assert len(events) == 1
        assert events[0].delivery_attempts == 1
        assert events[0].delivery_status == "failed"
        assert events[0].payload["_last_error"] == "boom"  # type: ignore[index]

    async def test_move_to_dead_letter(self) -> None:
        repo = InMemoryOutboxRepository()
        repo.add(_make_event(seq=1))
        await repo.move_to_dead_letter("t-1", 1, attempts=8, last_error="exhausted")
        events = await repo.list_pending(limit=10)
        assert events == []
        assert len(repo.dead_letters) == 1
        assert repo.dead_letters[0]["last_error"] == "exhausted"


# ---------------------------------------------------------------------------
# OutboxWorker state machine
# ---------------------------------------------------------------------------


class _SuccessDispatcher:
    def __init__(self) -> None:
        self.dispatched: list[OutboxEvent] = []

    async def dispatch(self, event: OutboxEvent) -> None:
        self.dispatched.append(event)


class _AlwaysFailDispatcher:
    async def dispatch(self, event: OutboxEvent) -> None:
        raise DispatchError("downstream unreachable")


class _FlakyDispatcher:
    """前 N 次失败, 第 N+1 次成功。"""

    def __init__(self, fail_count: int) -> None:
        self._fail_count = fail_count
        self._attempt = 0
        self.dispatched: list[OutboxEvent] = []

    async def dispatch(self, event: OutboxEvent) -> None:
        self._attempt += 1
        if self._attempt <= self._fail_count:
            raise DispatchError(f"attempt {self._attempt} failed")
        self.dispatched.append(event)


class TestOutboxWorker:
    async def test_tick_no_events(self) -> None:
        repo = InMemoryOutboxRepository()
        worker = OutboxWorker(repo, _SuccessDispatcher())  # type: ignore[arg-type]
        assert await worker.tick() == 0

    async def test_tick_dispatches_all_pending(self) -> None:
        repo = InMemoryOutboxRepository()
        repo.add(_make_event(seq=1))
        repo.add(_make_event(seq=2))
        dispatcher = _SuccessDispatcher()
        worker = OutboxWorker(repo, dispatcher)  # type: ignore[arg-type]

        n = await worker.tick()
        assert n == 2
        assert len(dispatcher.dispatched) == 2
        assert worker.stats.delivered == 2
        assert worker.stats.failed == 0

    async def test_tick_marks_failed(self) -> None:
        repo = InMemoryOutboxRepository()
        repo.add(_make_event(seq=1))
        worker = OutboxWorker(repo, _AlwaysFailDispatcher())  # type: ignore[arg-type]

        await worker.tick()
        assert worker.stats.failed == 1
        assert worker.stats.delivered == 0
        # 事件仍在 pending/failed 队列中,可继续重试
        events = await repo.list_pending(limit=10)
        assert len(events) == 1
        assert events[0].delivery_attempts == 1

    async def test_retry_succeeds_after_transient_failure(self) -> None:
        repo = InMemoryOutboxRepository()
        repo.add(_make_event(seq=1))
        # 前 2 次失败, 第 3 次成功
        dispatcher = _FlakyDispatcher(fail_count=2)
        worker = OutboxWorker(repo, dispatcher)  # type: ignore[arg-type]

        # 第一次 tick: 失败
        await worker.tick()
        assert worker.stats.failed == 1
        # 第二次 tick: 失败
        await worker.tick()
        assert worker.stats.failed == 2
        # 第三次 tick: 成功
        await worker.tick()
        assert worker.stats.delivered == 1
        assert len(dispatcher.dispatched) == 1

    async def test_dead_letter_after_max_attempts(self) -> None:
        """§4.4: 超 MAX_DELIVERY_ATTEMPTS=8 进死信。"""
        repo = InMemoryOutboxRepository()
        repo.add(_make_event(seq=1))
        worker = OutboxWorker(repo, _AlwaysFailDispatcher())  # type: ignore[arg-type]

        # 跑 8 次 tick, 每次都失败 → 第 8 次进入死信
        for _ in range(MAX_DELIVERY_ATTEMPTS):
            await worker.tick()

        assert worker.stats.dead_lettered == 1
        assert worker.stats.failed == MAX_DELIVERY_ATTEMPTS - 1
        # 死信表应有 1 条
        assert len(repo.dead_letters) == 1
        # 不再 pending
        assert await repo.list_pending(limit=10) == []

    async def test_unexpected_exception_does_not_crash_worker(self) -> None:
        """任何异常都不能让 worker 抛穿(§13.2 节点 17 失败处理)。"""

        class _BoomDispatcher:
            async def dispatch(self, event: OutboxEvent) -> None:
                raise RuntimeError("unexpected")

        repo = InMemoryOutboxRepository()
        repo.add(_make_event(seq=1))
        worker = OutboxWorker(repo, _BoomDispatcher())  # type: ignore[arg-type]

        # 不应抛异常
        await worker.tick()
        assert worker.stats.failed == 1


# ---------------------------------------------------------------------------
# Protocol duck-typing
# ---------------------------------------------------------------------------


def test_in_memory_repo_satisfies_protocol() -> None:
    assert isinstance(InMemoryOutboxRepository(), OutboxRepository)


def test_success_dispatcher_satisfies_protocol() -> None:
    assert isinstance(_SuccessDispatcher(), OutboxDispatcher)