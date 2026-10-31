"""同会话的**有序处理**（Router 方案 §4.2）—— 排队的契约。

⚠️ **三个机制** ✓（Router 方案 §4.2 ✓）：

| # | 机制 | 落点 |
|---|---|---|
| 1 | **序号分配** ✓ | `sequence.py` ✓ —— 会话行原子自增 ✓（跨 worker 有效 ✓） |
| 2 | **入队** ✓ | `session_turns.status = 'queued'` ✓ + `ingress_seq` ✓ |
| 3 | **放行** ✓ | 本模块 ✓ —— FIFO ✓ |

⚠️ **放行条件** ✓（两个都要满足 ✓）：

```
turn.ingress_seq == session.last_completed_seq + 1     ← 顺序 ✓
AND 该会话当前没有正在执行的轮次                        ← 互斥 ✓
```

⚠️ **权威是轮次行的状态 CAS** ✓（决策 #9 ✓）—— 只有把
``status`` 从 ``queued`` **原子地**改成 ``running`` 的那个 worker 才能执行
✓（不需要任何跨事务锁 ✓ —— 事务提交即释放会让互斥形同虚设 ✗✗）。

⚠️ **审批挂起不占执行位** ✓（决策 #6 ✓）—— 等待审批的轮次状态是
``waiting`` ✓（不是 ``running`` ✓）—— **不阻塞新消息** ✓
（否则「等审批 → 后续消息全堵死」✗✗）。

⚠️ **快照可能落后 —— 必须有兜底** ✓（Router 方案 §4.2 ✓）——
``session.last_completed_seq`` 是**冗余快照** ✓，权威值在 ``session_turns``
✓。两者不一致时**放行条件永远不成立** ✗（队列卡死 ✓ 且**无报错** ✓ ——
极难排查 ✓）。因此有**两级判定** ✓：

| 级 | 条件 | 用途 |
|---|---|---|
| **快路径** ✓ | 快照值成立 ✓ | O(1) ✓ —— 正常路径 ✓ |
| **兜底路径** ✓ | 快照不成立 ✓ 但 ``session_turns`` 里有更大的 ``succeeded`` ✓ | **以权威值为准放行** ✓ + 修快照 ✓ + 计数告警 ✓ |

⚠️ **队列上限与超时** ✓（决策 #7 ✓）—— N = 5 条 ✓ / T = 60 秒 ✓；
超限返回**明确错误码** ✓（``QUEUE_FULL`` ✓ / ``QUEUE_TIMEOUT`` ✓）——
**不得静默丢弃** ✓（超限的轮次落 ``cancelled`` ✓ —— 可查 ✓）。
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum
from time import monotonic
from typing import Protocol, runtime_checkable
from uuid import UUID

from qzdap_kernel.errors import AppError
from qzdap_observability.metrics import (
    record_router_concurrency_rejected,
    record_router_queue_wait,
)
from qzdap_schema.dtos.errors import ErrorCode

#: **单会话排队上限** ✓（决策 #7 ✓ —— N = 5 条 ✓）。
QUEUE_MAX_DEPTH = 5

#: **最长等待时间** ✓（决策 #7 ✓ —— T = 60 秒 ✓）。
QUEUE_MAX_WAIT_SECONDS = 60.0

#: **轮询间隔** ✓（排队是短时的 ✓ —— 20ms ✓ 足够及时 ✓ 又不压库 ✓）。
QUEUE_POLL_SECONDS = 0.02


class QueueOutcome(StrEnum):
    """**排队的结果** ✓。"""

    #: **轮到我了** ✓（可以执行 ✓）。
    RELEASED = "released"
    #: **还没轮到** ✓（继续等 ✓ —— 不是错误 ✓）。
    WAITING = "waiting"
    #: **队列满了** ✓（N 条上限 ✓）—— 明确错误 ✓ 不静默丢弃 ✓。
    FULL = "full"
    #: **等超时了** ✓（T 秒上限 ✓）—— 明确错误 ✓ 不静默丢弃 ✓。
    TIMEOUT = "timeout"
    #: **用户取消了** ✓（排队期间取消 ✓）。
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class QueueDecision:
    """**一次放行判定** ✓。"""

    outcome: QueueOutcome
    #: **队列位置** ✓（1 = 下一个就跑 ✓）。
    position: int = 0
    #: **已经等了多久** ✓（毫秒 ✓）。
    waited_ms: int = 0
    #: **预计还要等多久** ✓（秒 ✓ —— 估不出来就 0 ✓）。
    estimated_wait_seconds: float = 0.0


class QueueCancelled(RuntimeError):
    """**排队期间被取消** ✓（用户点了停止 ✓）。

    ⚠️ **契约层不认识轮次编排** ✓ —— 由调用方翻译成自己的取消信号 ✓。
    """


class QueueFullError(AppError):
    """**队列满了** ✓（N 条上限 ✓ —— 决策 #7 ✓）。

    ⚠️ **不静默丢弃** ✓ —— 轮次落 ``cancelled`` ✓（可查 ✓）。
    """

    code = ErrorCode.QUEUE_FULL.value
    status = 429


class QueueTimeoutError(AppError):
    """**排队等超时了** ✓（T 秒上限 ✓ —— 决策 #7 ✓）。"""

    code = ErrorCode.QUEUE_TIMEOUT.value
    status = 503


@runtime_checkable
class TurnQueuePort(Protocol):
    """**排队的端口** ✓（实现在模块侧 ✓ —— SQL 归那一侧 ✓）。"""

    async def try_release(
        self,
        *,
        tenant_id: UUID,
        session_id: UUID,
        turn_id: UUID,
        ingress_seq: int,
    ) -> QueueDecision:
        """**试一次放行** ✓ —— 成功就**已经把轮次改成 running 了** ✓。

        ⚠️ **快路径 + 兜底路径都在实现里** ✓（Router 方案 §4.2 ✓）——
        兜底命中要**修快照** ✓ + **计数告警** ✓。
        """
        ...

    async def queue_depth(self, *, tenant_id: UUID, session_id: UUID) -> int:
        """**当前排队的轮次数** ✓（N 条上限的判据 ✓）。"""
        ...

    async def queue_position(self, *, tenant_id: UUID, session_id: UUID, ingress_seq: int) -> int:
        """**我排在第几个** ✓（1 = 下一个 ✓）。"""
        ...


async def wait_for_turn_slot(
    port: TurnQueuePort,
    *,
    tenant_id: UUID,
    session_id: UUID,
    turn_id: UUID,
    ingress_seq: int,
    max_depth: int = QUEUE_MAX_DEPTH,
    max_wait_seconds: float = QUEUE_MAX_WAIT_SECONDS,
    poll_seconds: float = QUEUE_POLL_SECONDS,
    cancelled: Callable[[], Awaitable[bool]] | None = None,
) -> AsyncIterator[QueueDecision]:
    """**等自己的 FIFO 位** ✓（决策 #1「S1 严格排队」✓）。

    ⚠️ **它是异步生成器** ✓ —— 等待期间**要能往前端发「排队中」** ✓
    （否则前端只能转圈到首 chunk 到达 ✗✗ —— Router 方案 §0.7 ✓）。
    产出的每一条都是「还在等」的状态 ✓；**放行时正常结束** ✓。

    ⚠️ **上限与超时都抛明确错误** ✓（决策 #7 ✓）—— **不静默丢弃** ✓：
    队列满了抛 :class:`QueueFullError` ✓；等超时抛 :class:`QueueTimeoutError` ✓。

    ⚠️ **取消随时生效** ✓ —— 用户在排队期间取消 ✓ → 抛 ``TurnCancelled`` ✓
    （由调用方翻译 ✓ —— 契约层不认识轮次编排 ✓）。
    """
    started = monotonic()
    depth = await port.queue_depth(tenant_id=tenant_id, session_id=session_id)
    if depth >= max_depth:
        record_router_concurrency_rejected(reason="queue_full")
        raise QueueFullError(f"session {session_id} queue is full ({depth} waiting)")
    while True:
        decision = await port.try_release(
            tenant_id=tenant_id,
            session_id=session_id,
            turn_id=turn_id,
            ingress_seq=ingress_seq,
        )
        waited = int((monotonic() - started) * 1000)
        if decision.outcome is QueueOutcome.RELEASED:
            record_router_queue_wait(tenant_id=str(tenant_id), waited_s=waited / 1000)
            return
        if cancelled is not None and await cancelled():
            raise QueueCancelled("用户在排队期间取消了这一轮")
        if monotonic() - started >= max_wait_seconds:
            record_router_concurrency_rejected(reason="queue_timeout")
            raise QueueTimeoutError(f"session {session_id} queue wait exceeded {max_wait_seconds}s")
        yield QueueDecision(
            outcome=QueueOutcome.WAITING,
            position=decision.position,
            waited_ms=waited,
            estimated_wait_seconds=decision.estimated_wait_seconds,
        )
        await asyncio.sleep(poll_seconds)


__all__ = [
    "QUEUE_MAX_DEPTH",
    "QUEUE_MAX_WAIT_SECONDS",
    "QUEUE_POLL_SECONDS",
    "QueueCancelled",
    "QueueDecision",
    "QueueFullError",
    "QueueOutcome",
    "QueueTimeoutError",
    "TurnQueuePort",
    "wait_for_turn_slot",
]
