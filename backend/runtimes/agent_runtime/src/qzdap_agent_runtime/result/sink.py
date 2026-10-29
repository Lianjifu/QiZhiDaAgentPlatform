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
from typing import TYPE_CHECKING

from ..gateway.outbound import DeliveryOutcome, OutboundTarget, ResultSink

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from .events import (
        ResultEvent,
    )


class DispatchError(Exception):
    """单个 sink 投递失败（其他 sink 继续投递）。"""


# ⚠️ **ResultSink 的定义只有一份** —— 在 ``gateway/outbound.py``（Gateway ① 的
# 出站端口）。本模块不再自定义协议：两个同名协议 = 两套形状 = 迟早漂移。
# 本模块的内存 sink 按该协议实现（``deliver`` / ``replay``）。


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

    async def deliver(
        self, event: ResultEvent, *, target: OutboundTarget | None = None
    ) -> DeliveryOutcome:
        """Gateway 出站端口的实现 —— 内存收集（供 SSE 消费 / 重放）。

        ``target`` 对内存 sink 无意义（它不投递到渠道），但**签名必须与端口一致**
        —— 这正是「只有一个 ResultSink 定义」的价值。
        """
        _ = target
        async with self._lock:
            turn_id = event.turn_id
            if event.seq == 0:
                # 自动分配 seq（如果上游没指定）
                self._seq_counters[turn_id] += 1
                # 注意：事件不可变，必须替换
                object.__setattr__(event, "seq", self._seq_counters[turn_id])
            else:
                # 显式 seq: 始终更新 latest_seq 为 max
                self._seq_counters[turn_id] = max(
                    self._seq_counters[turn_id], event.seq
                )
            self._events[turn_id].append(event)
        return DeliveryOutcome(status="sent")

    async def dispatch(self, event: ResultEvent) -> None:
        """旧调用名 —— 保留一个别名，避免 X1 包内的旧调用点全部改写。"""
        await self.deliver(event)

    def get_events(self, turn_id: str, after_seq: int = 0) -> list[ResultEvent]:
        """SSE 重放: 取 seq > after_seq 的所有事件。"""
        events = self._events.get(turn_id, [])
        return [e for e in events if e.seq > after_seq]

    async def replay(self, turn_id: str, after_seq: int = 0) -> AsyncIterator[ResultEvent]:
        """Gateway 出站端口的重放实现 —— 按 seq 升序吐出该轮的事件。"""
        for event in self.get_events(turn_id, after_seq):
            yield event

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