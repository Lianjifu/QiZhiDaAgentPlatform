"""Result sink + ResultDispatcher (§3.2 / §5.9 / §13.5)。

Stage 5 PR A 范围：

- `ResultSink` Protocol：抽象下游 sink (SSE / Channel / Webhook)
- `InMemoryResultSink`：进程内实现，收集事件供 SSE 消费
- `SseReplayBuffer`：按 (turn_id, after_seq) 重放事件 (§4.4 Last-Event-ID)
- `ResultDispatcher`：fan out ResultEvent 到多个 sink
  - 一个 sink 失败不影响其他 sink
  - 错误码：SSE 错 / Channel 错 / Webhook 错各自独立降级
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any, Protocol, runtime_checkable
from uuid import uuid4

from .events import (
    ApprovalRequiredEvent,
    ContextCompactedEvent,
    DoneEvent,
    ErrorEvent,
    KnowledgeSearchEvent,
    MemoryWriteEvent,
    MessageEvent,
    ResultEvent,
    SkillInvocationEvent,
    ToolCallEvent,
    ToolResultEvent,
    UsageEvent,
)


class DispatchError(Exception):
    """单个 sink 投递失败（其他 sink 继续投递）。"""


@runtime_checkable
class ResultSink(Protocol):
    """§3.2 / §13.5 单个下游 sink (SSE / IM / Webhook)。"""

    async def dispatch(self, event: ResultEvent) -> None:
        """投递一条 ResultEvent;失败抛 DispatchError。"""
        ...


# ---------------------------------------------------------------------------
# InMemoryResultSink (用于单测 + 本地 dev)
# ---------------------------------------------------------------------------


class InMemoryResultSink:
    """进程内 sink, 收集所有事件供 SSE 客户端消费/重放。"""

    def __init__(self) -> None:
        # 按 (turn_id) 分组的事件流
        self._events: dict[str, list[ResultEvent]] = defaultdict(list)
        self._seq_counters: dict[str, int] = defaultdict(int)
        self._lock = asyncio.Lock()

    async def dispatch(self, event: ResultEvent) -> None:
        async with self._lock:
            turn_id = event.turn_id
            if event.seq == 0:
                # 自动分配 seq（如果上游没指定）
                self._seq_counters[turn_id] += 1
                # 注意：dispatch 不可变事件，必须替换
                object.__setattr__(event, "seq", self._seq_counters[turn_id])
            else:
                # 显式 seq: 始终更新 latest_seq 为 max
                if event.seq > self._seq_counters[turn_id]:
                    self._seq_counters[turn_id] = event.seq
            self._events[turn_id].append(event)

    def get_events(self, turn_id: str, after_seq: int = 0) -> list[ResultEvent]:
        """SSE 重放: 取 seq > after_seq 的所有事件。"""
        events = self._events.get(turn_id, [])
        return [e for e in events if e.seq > after_seq]

    def latest_seq(self, turn_id: str) -> int:
        return self._seq_counters.get(turn_id, 0)

    def all_turns(self) -> list[str]:
        return list(self._events.keys())


# ---------------------------------------------------------------------------
# ResultDispatcher
# ---------------------------------------------------------------------------


class ResultDispatcher:
    """§3.2 ResultDispatcher — fan out ResultEvent 到多个 sink。

    关键约束（§4.4）：

    - 一个 sink 失败不影响其他 sink
    - 失败仅记日志，不抛穿 main path
    - 顺序保证：单 turn 内的事件按 seq 升序投递
    """

    def __init__(self, sinks: list[ResultSink] | None = None) -> None:
        self._sinks: list[ResultSink] = list(sinks or [])

    def register(self, sink: ResultSink) -> None:
        self._sinks.append(sink)

    async def dispatch(self, event: ResultEvent) -> dict[str, bool]:
        """投递 event 到所有 sink。

        Returns:
            {sink_name: success_bool} 映射。
            任一 sink 失败不阻塞其他 sink。
        """
        results: dict[str, bool] = {}
        for sink in self._sinks:
            name = type(sink).__name__
            try:
                await sink.dispatch(event)
                results[name] = True
            except Exception as exc:  # noqa: BLE001
                # §5.9 degraded 标志: 单个 sink 失败不阻塞其他
                results[name] = False
                import logging
                logging.getLogger(__name__).warning(
                    "result dispatch failed: sink=%s event=%s error=%s",
                    name, type(event).__name__, exc,
                )
        return results

    @property
    def sinks(self) -> list[ResultSink]:
        return list(self._sinks)


__all__ = [
    "DispatchError",
    "InMemoryResultSink",
    "ResultDispatcher",
    "ResultSink",
]