"""Tests for Stage 5 PR A: ResultSink + ResultDispatcher + InMemoryResultSink。"""

from __future__ import annotations

import asyncio

import pytest

from qzdap_agent_runtime.result import (
    DispatchError,
    InMemoryResultSink,
    MessageEvent,
    ResultDispatcher,
    ResultEvent,
    ResultSink,
)


# ---------------------------------------------------------------------------
# Protocol duck-typing
# ---------------------------------------------------------------------------


def test_in_memory_sink_satisfies_protocol() -> None:
    assert isinstance(InMemoryResultSink(), ResultSink)


def test_result_dispatcher_is_not_a_sink() -> None:
    """ResultDispatcher 本身不是 sink (它是 fan-out), 鸭子类型不入 isinstance。

    注: 由于 runtime_checkable Protocol 的结构化检查, ResultDispatcher
    因为有 dispatch 方法可能被误识为 sink；这并非设计意图, 这里仅作
    文档记录。
    """
    d = ResultDispatcher()
    assert d.sinks == []  # dispatcher 没有任何内置 sink


# ---------------------------------------------------------------------------
# InMemoryResultSink
# ---------------------------------------------------------------------------


def _make_event(seq: int = 0, turn_id: str = "t-1") -> ResultEvent:
    return MessageEvent(turn_id=turn_id, seq=seq, event_id=f"e-{seq}", delta=f"d{seq}")


class TestInMemoryResultSink:
    async def test_dispatch_collects_event(self) -> None:
        sink = InMemoryResultSink()
        ev = _make_event(seq=1)
        await sink.dispatch(ev)
        events = sink.get_events("t-1")
        assert len(events) == 1
        assert events[0].seq == 1
        assert events[0].delta == "d1"

    async def test_dispatch_auto_assigns_seq_when_zero(self) -> None:
        """seq=0 时由 sink 自动分配。"""
        sink = InMemoryResultSink()
        await sink.dispatch(_make_event(seq=0))
        await sink.dispatch(_make_event(seq=0))
        events = sink.get_events("t-1")
        # 自动分配 1, 2
        assert [e.seq for e in events] == [1, 2]

    async def test_dispatch_respects_explicit_seq(self) -> None:
        sink = InMemoryResultSink()
        await sink.dispatch(_make_event(seq=5))
        await sink.dispatch(_make_event(seq=3))  # 显式 seq 不重排
        events = sink.get_events("t-1")
        # 显式 seq 保留原值
        assert [e.seq for e in events] == [5, 3]

    def test_get_events_filter_by_after_seq(self) -> None:
        """§4.4 Last-Event-ID 重放: 取 seq > after_seq。"""
        sink = InMemoryResultSink()
        for i in range(1, 6):
            asyncio.run(sink.dispatch(_make_event(seq=i)))
        events = sink.get_events("t-1", after_seq=3)
        assert [e.seq for e in events] == [4, 5]

    def test_get_events_empty_turn(self) -> None:
        sink = InMemoryResultSink()
        assert sink.get_events("never-seen") == []

    def test_latest_seq(self) -> None:
        sink = InMemoryResultSink()
        asyncio.run(sink.dispatch(_make_event(seq=7)))
        assert sink.latest_seq("t-1") == 7
        assert sink.latest_seq("never-seen") == 0

    def test_all_turns(self) -> None:
        sink = InMemoryResultSink()
        asyncio.run(sink.dispatch(_make_event(turn_id="t-1")))
        asyncio.run(sink.dispatch(_make_event(turn_id="t-2")))
        assert set(sink.all_turns()) == {"t-1", "t-2"}


# ---------------------------------------------------------------------------
# ResultDispatcher
# ---------------------------------------------------------------------------


class _SuccessSink:
    def __init__(self) -> None:
        self.received: list[ResultEvent] = []

    async def dispatch(self, event: ResultEvent) -> None:
        self.received.append(event)


class _FailingSink:
    """FailingSink: 投递时抛 DispatchError。"""

    async def dispatch(self, event: ResultEvent) -> None:
        raise DispatchError("downstream unreachable")


class TestResultDispatcher:
    async def test_dispatch_to_single_sink(self) -> None:
        sink = _SuccessSink()
        d = ResultDispatcher([sink])
        ev = _make_event(seq=1)
        results = await d.dispatch(ev)
        assert results == {"_SuccessSink": True}
        assert sink.received == [ev]

    async def test_dispatch_to_multiple_sinks(self) -> None:
        a, b = _SuccessSink(), _SuccessSink()
        d = ResultDispatcher([a, b])
        ev = _make_event(seq=1)
        results = await d.dispatch(ev)
        assert results == {"_SuccessSink": True, "_SuccessSink": True}
        assert a.received == [ev]
        assert b.received == [ev]

    async def test_one_sink_fails_does_not_block_others(self) -> None:
        """§4.4 关键约束: 单 sink 失败不影响其他 sink。"""
        good = _SuccessSink()
        bad = _FailingSink()
        d = ResultDispatcher([bad, good])  # 失败 sink 在前
        ev = _make_event(seq=1)
        results = await d.dispatch(ev)
        # bad 失败, good 成功 (type(sink).__name__ 命名)
        bad_name = type(bad).__name__
        good_name = type(good).__name__
        assert results[bad_name] is False
        assert results[good_name] is True
        # good sink 仍收到事件
        assert good.received == [ev]

    async def test_all_sinks_failing_returns_all_false(self) -> None:
        d = ResultDispatcher([_FailingSink(), _FailingSink()])
        results = await d.dispatch(_make_event(seq=1))
        assert all(v is False for v in results.values())

    async def test_register_sink_runtime(self) -> None:
        d = ResultDispatcher()
        sink = _SuccessSink()
        d.register(sink)
        await d.dispatch(_make_event(seq=1))
        assert len(sink.received) == 1

    async def test_no_sinks_dispatches_to_nothing(self) -> None:
        d = ResultDispatcher()
        results = await d.dispatch(_make_event(seq=1))
        assert results == {}

    async def test_sink_raising_unexpected_exception_does_not_crash(self) -> None:
        """任何异常都按 sink 失败处理(不抛穿 dispatcher)。"""

        class _BoomSink:
            async def dispatch(self, event: ResultEvent) -> None:
                raise RuntimeError("unexpected")

        good = _SuccessSink()
        d = ResultDispatcher([_BoomSink(), good])
        results = await d.dispatch(_make_event(seq=1))
        assert results["_BoomSink"] is False
        assert results["_SuccessSink"] is True

    def test_sinks_property_returns_copy(self) -> None:
        """sinks 属性必须返回副本, 外部修改不影响内部列表。"""
        d = ResultDispatcher([_SuccessSink()])
        sinks = d.sinks
        sinks.clear()
        assert len(d.sinks) == 1