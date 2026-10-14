"""Outbox 层：§4.4 决议 — 事件投递状态机 + 死信处理。

Stage 2 PR D 范围：

- `OutboxEvent` dataclass：从 `session_events` 表读出 (turn_id, seq, payload, ...)
- `OutboxRepository` Protocol：抽象 outbox 表读写（生产 Postgres，单测 InMemory）
- `OutboxDispatcher` Protocol：抽象下游 sink（SSE / Channel / Webhook）
- `OutboxWorker` 状态机：

    PENDING → DELIVERED (sink 成功)
    PENDING → FAILED (sink 失败, 重试计数 +1)
    FAILED → DELIVERED (重试成功)
    FAILED → DEAD_LETTER (超 MAX_DELIVERY_ATTEMPTS=8, 写入 outbox_dead_letters)

- §4.4 关键约束：

    - 重试：指数退避 + jitter, 初始 1s, 上限 5min
    - 顺序保证：同一 (turn_id, seq) 严格有序
    - 副作用：模型结果 / 工具结果 / 记忆写入必须在 outbox 入队前提交
    - 失败不阻塞 turn 成功状态
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# §4.4 配置
# ---------------------------------------------------------------------------

MAX_DELIVERY_ATTEMPTS = 8
RETRY_BASE_SECONDS = 1.0
RETRY_MAX_SECONDS = 300.0  # 5 分钟


# ---------------------------------------------------------------------------
# Outbox 事件 / 状态
# ---------------------------------------------------------------------------


DeliveryStatus = str  # 'pending' | 'delivered' | 'failed' | 'dead_letter'


@dataclass(frozen=True, slots=True)
class OutboxEvent:
    """从 session_events 表读出的一条事件。"""

    turn_id: str
    seq: int
    event_type: str
    payload: dict[str, Any]
    delivery_status: DeliveryStatus
    delivery_attempts: int
    delivered_at: datetime | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# Repository / Dispatcher 协议
# ---------------------------------------------------------------------------


@runtime_checkable
class OutboxRepository(Protocol):
    """§4.4 outbox 表读写抽象。生产用 Postgres 实现。"""

    async def list_pending(self, limit: int = 100) -> list[OutboxEvent]:
        """查询 delivery_status=pending 的事件,按 (turn_id, seq) 升序。"""
        ...

    async def mark_delivered(self, turn_id: str, seq: int) -> None:
        """标记事件已投递:delivery_status='delivered', delivered_at=now()。"""
        ...

    async def mark_failed(
        self, turn_id: str, seq: int, attempts: int, last_error: str
    ) -> None:
        """标记事件投递失败,attempts +1。"""
        ...

    async def move_to_dead_letter(
        self, turn_id: str, seq: int, attempts: int, last_error: str
    ) -> None:
        """§4.4 超 MAX_DELIVERY_ATTEMPTS 时,从 session_events 删除并写入
        outbox_dead_letters 表。"""
        ...


@runtime_checkable
class OutboxDispatcher(Protocol):
    """§4.4 下游 sink: SSE / Channel / Webhook。"""

    async def dispatch(self, event: OutboxEvent) -> None:
        """投递事件;失败抛 DispatchError(由 worker 转为 FAILED 状态)。"""
        ...


class DispatchError(Exception):
    """outbox dispatcher 失败时抛此异常(由 worker catch 后转为 FAILED)。"""


# ---------------------------------------------------------------------------
# In-memory 实现（单测 / 本地 dev）
# ---------------------------------------------------------------------------


class InMemoryOutboxRepository:
    """进程内 outbox repository,用于单测。"""

    def __init__(self) -> None:
        # 顺序：按 (turn_id, seq) 升序
        self._events: list[OutboxEvent] = []
        self._dead_letters: list[dict[str, Any]] = []

    def add(self, event: OutboxEvent) -> None:
        """单测辅助:入队事件(模拟 persist_result 写入)。"""
        self._events.append(event)
        self._events.sort(key=lambda e: (e.turn_id, e.seq))

    async def list_pending(self, limit: int = 100) -> list[OutboxEvent]:
        return [
            e
            for e in self._events
            if e.delivery_status in ("pending", "failed")
            and e.delivery_attempts < MAX_DELIVERY_ATTEMPTS
        ][:limit]

    async def mark_delivered(self, turn_id: str, seq: int) -> None:
        self._events = [
            OutboxEvent(
                turn_id=e.turn_id,
                seq=e.seq,
                event_type=e.event_type,
                payload=e.payload,
                delivery_status="delivered",
                delivery_attempts=e.delivery_attempts,
                delivered_at=datetime.now(timezone.utc),
                created_at=e.created_at,
            )
            if e.turn_id == turn_id and e.seq == seq
            else e
            for e in self._events
        ]

    async def mark_failed(
        self, turn_id: str, seq: int, attempts: int, last_error: str
    ) -> None:
        self._events = [
            OutboxEvent(
                turn_id=e.turn_id,
                seq=e.seq,
                event_type=e.event_type,
                payload={**e.payload, "_last_error": last_error},
                delivery_status="failed",
                delivery_attempts=attempts,
                delivered_at=e.delivered_at,
                created_at=e.created_at,
            )
            if e.turn_id == turn_id and e.seq == seq
            else e
            for e in self._events
        ]

    async def move_to_dead_letter(
        self, turn_id: str, seq: int, attempts: int, last_error: str
    ) -> None:
        target = next(
            (
                e
                for e in self._events
                if e.turn_id == turn_id and e.seq == seq
            ),
            None,
        )
        if target is None:
            return
        self._dead_letters.append(
            {
                "turn_id": turn_id,
                "seq": seq,
                "attempt": attempts,
                "event_type": target.event_type,
                "payload": target.payload,
                "last_error": last_error,
            }
        )
        self._events = [
            e for e in self._events if not (e.turn_id == turn_id and e.seq == seq)
        ]

    @property
    def dead_letters(self) -> list[dict[str, Any]]:
        return list(self._dead_letters)


# ---------------------------------------------------------------------------
# 退避计算（指数 + jitter）
# ---------------------------------------------------------------------------


def compute_retry_delay(attempt: int) -> float:
    """§4.4 重试策略: 指数退避 + jitter, 初始 1s, 上限 5min。

    Args:
        attempt: 当前失败次数 (从 1 开始)。

    Returns:
        等待秒数, [0, 300] 之间 (jitter 之后再 clamp, 不超过上限)。
    """
    if attempt < 1:
        attempt = 1
    base = RETRY_BASE_SECONDS * (2 ** (attempt - 1))
    capped = min(base, RETRY_MAX_SECONDS)
    # jitter: ±20% 抖动避免 thundering herd
    jitter = capped * 0.2 * (random.random() * 2 - 1)
    return max(0.0, min(RETRY_MAX_SECONDS, capped + jitter))


# ---------------------------------------------------------------------------
# OutboxWorker
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class WorkerStats:
    """worker 运行时统计(观测指标)。"""

    processed: int = 0
    delivered: int = 0
    failed: int = 0
    dead_lettered: int = 0


class OutboxWorker:
    """§4.4 outbox worker: 拉取 pending 事件 → dispatch → 更新状态。"""

    def __init__(
        self,
        repo: OutboxRepository,
        dispatcher: OutboxDispatcher,
    ) -> None:
        self._repo = repo
        self._dispatcher = dispatcher
        self._stats = WorkerStats()

    @property
    def stats(self) -> WorkerStats:
        return self._stats

    async def tick(self) -> int:
        """跑一轮 worker: 拉取一批 pending 事件并尝试投递。

        Returns:
            本轮处理的事件数。
        """
        events = await self._repo.list_pending(limit=100)
        if not events:
            return 0

        for event in events:
            await self._process_one(event)
        return len(events)

    async def _process_one(self, event: OutboxEvent) -> None:
        """处理单条事件,根据投递结果走状态机。"""
        next_attempt = event.delivery_attempts + 1
        try:
            await self._dispatcher.dispatch(event)
        except DispatchError as exc:
            await self._handle_failure(event, next_attempt, str(exc))
            return  # 关键: 失败路径必须 return, 不能落到成功分支
        except Exception as exc:  # noqa: BLE001
            # 任何其他异常都按 FAILED 处理(不抛穿 worker)
            logger.exception(
                "outbox dispatch unexpected error: turn_id=%s seq=%s",
                event.turn_id, event.seq,
            )
            await self._handle_failure(event, next_attempt, str(exc))
            return
        # 成功
        await self._repo.mark_delivered(event.turn_id, event.seq)
        self._stats.delivered += 1
        self._stats.processed += 1

    async def _handle_failure(
        self, event: OutboxEvent, attempts: int, error: str
    ) -> None:
        """§4.4 状态机: FAILED 或 DEAD_LETTER。"""
        if attempts >= MAX_DELIVERY_ATTEMPTS:
            # §4.4: 超 MAX_DELIVERY_ATTEMPTS=8 进死信
            await self._repo.move_to_dead_letter(
                event.turn_id, event.seq, attempts, error
            )
            self._stats.dead_lettered += 1
            logger.warning(
                "outbox dead-letter: turn_id=%s seq=%s attempts=%s error=%s",
                event.turn_id, event.seq, attempts, error,
            )
        else:
            await self._repo.mark_failed(
                event.turn_id, event.seq, attempts, error
            )
            self._stats.failed += 1
        self._stats.processed += 1


__all__ = [
    "DispatchError",
    "InMemoryOutboxRepository",
    "MAX_DELIVERY_ATTEMPTS",
    "OutboxDispatcher",
    "OutboxEvent",
    "OutboxRepository",
    "OutboxWorker",
    "RETRY_BASE_SECONDS",
    "RETRY_MAX_SECONDS",
    "WorkerStats",
    "compute_retry_delay",
]