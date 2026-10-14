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


# ---------------------------------------------------------------------------
# OutboxToSinkAdapter (Stage 5 PR B)
# ---------------------------------------------------------------------------


class OutboxToSinkAdapter:
    """§4.4 / §13.5 adapter: 把 OutboxEvent 推给 ResultSink 集合。

    - 每个 OutboxEvent 转换成对应 ResultEvent 类型
    - 转换失败 / sink 失败 不抛穿 worker
    - 用于 outbox_dead_letters 首次写入 (Stage 5 退出条件)
    """

    def __init__(self, sinks: Any) -> None:
        if hasattr(sinks, "sinks"):
            self._sinks: list[Any] = list(sinks.sinks)
        else:
            self._sinks = list(sinks)

    async def dispatch(self, event: Any) -> None:
        from ..result.events import (
            MessageEvent, ToolCallEvent, ToolResultEvent, ErrorEvent,
            SkillInvocationEvent, MemoryWriteEvent, KnowledgeSearchEvent,
            ContextCompactedEvent, ApprovalRequiredEvent, UsageEvent, DoneEvent,
        )

        ev_type = getattr(event, "event_type", "message")
        payload = getattr(event, "payload", {}) or {}
        turn_id = getattr(event, "turn_id", "unknown")
        seq = getattr(event, "seq", 0)
        event_id = f"outbox-{turn_id}-{seq}"

        result_event: Any = None
        if ev_type == "message":
            result_event = MessageEvent(
                turn_id=turn_id, seq=seq, event_id=event_id,
                delta=str(payload.get("content", "")),
            )
        elif ev_type == "tool_call":
            result_event = ToolCallEvent(
                turn_id=turn_id, seq=seq, event_id=event_id,
                tool_name=str(payload.get("tool_name", "")),
                tool_call_id=str(payload.get("tool_call_id", "")),
                arguments=payload.get("arguments", {}),
            )
        elif ev_type == "tool_result":
            result_event = ToolResultEvent(
                turn_id=turn_id, seq=seq, event_id=event_id,
                tool_call_id=str(payload.get("tool_call_id", "")),
                output=payload.get("output"),
                is_error=bool(payload.get("is_error", False)),
                latency_ms=int(payload.get("latency_ms", 0)),
            )
        elif ev_type == "skill_invocation":
            result_event = SkillInvocationEvent(
                turn_id=turn_id, seq=seq, event_id=event_id,
                invocation_id=str(payload.get("invocation_id", "")),
                skill=str(payload.get("skill", "")),
                status=str(payload.get("status", "started")),
            )
        elif ev_type == "memory_write":
            result_event = MemoryWriteEvent(
                turn_id=turn_id, seq=seq, event_id=event_id,
                layer=str(payload.get("layer", "l1")),
                source_turn_id=str(payload.get("source_turn_id", "")),
                preview=str(payload.get("preview", "")),
            )
        elif ev_type == "knowledge_search":
            result_event = KnowledgeSearchEvent(
                turn_id=turn_id, seq=seq, event_id=event_id,
                query_hash=str(payload.get("query_hash", "")),
                hits=payload.get("hits", []),
                citations=payload.get("citations", []),
                degraded=bool(payload.get("degraded", False)),
            )
        elif ev_type == "context_compacted":
            result_event = ContextCompactedEvent(
                turn_id=turn_id, seq=seq, event_id=event_id,
                tokens_before=int(payload.get("tokens_before", 0)),
                tokens_after=int(payload.get("tokens_after", 0)),
                removed_ids=payload.get("removed_ids", []),
            )
        elif ev_type == "approval_required":
            result_event = ApprovalRequiredEvent(
                turn_id=turn_id, seq=seq, event_id=event_id,
                approval_id=str(payload.get("approval_id", "")),
                tool_call_id=str(payload.get("tool_call_id", "")),
                tool=str(payload.get("tool", "")),
                args_preview=str(payload.get("args_preview", "")),
                reason=str(payload.get("reason", "")),
                expires_at=str(payload.get("expires_at", "2026-10-15T10:15:00Z")),
            )
        elif ev_type == "usage":
            result_event = UsageEvent(
                turn_id=turn_id, seq=seq, event_id=event_id,
                input_tokens=int(payload.get("input_tokens", 0)),
                output_tokens=int(payload.get("output_tokens", 0)),
                cache_tokens=int(payload.get("cache_tokens", 0)),
                cost_usd=payload.get("cost_usd"),
                cost_unknown=bool(payload.get("cost_unknown", True)),
                tenant_id=str(payload.get("tenant_id", "")),
                workspace_id=str(payload.get("workspace_id", "")),
                user_id=str(payload.get("user_id", "")),
                agent_id=str(payload.get("agent_id", "")),
                agent_version=str(payload.get("agent_version", "")),
                model_version=str(payload.get("model_version", "")),
                retry_count=int(payload.get("retry_count", 0)),
            )
        elif ev_type == "done":
            result_event = DoneEvent(
                turn_id=turn_id, seq=seq, event_id=event_id,
                final_message=str(payload.get("final_message", "")),
                status=str(payload.get("status", "succeeded")),
                agent_version=str(payload.get("agent_version", "")),
                model_version=str(payload.get("model_version", "")),
            )
        else:
            result_event = ErrorEvent(
                turn_id=turn_id, seq=seq, event_id=event_id,
                error_code=str(payload.get("error_code", "INTERNAL_ERROR")),
                safe_message=str(payload.get("message", ev_type)),
                retriable=False,
            )

        import logging
        for sink in self._sinks:
            name = type(sink).__name__
            try:
                await sink.dispatch(result_event)
            except Exception as exc:  # noqa: BLE001
                logging.getLogger(__name__).warning(
                    "OutboxToSink dispatch failed: sink=%s error=%s", name, exc,
                )


__all__ = [
    "DispatchError",
    "InMemoryOutboxRepository",
    "MAX_DELIVERY_ATTEMPTS",
    "OutboxDispatcher",
    "OutboxEvent",
    "OutboxRepository",
    "OutboxToSinkAdapter",
    "OutboxWorker",
    "RETRY_BASE_SECONDS",
    "RETRY_MAX_SECONDS",
    "WorkerStats",
    "compute_retry_delay",
]