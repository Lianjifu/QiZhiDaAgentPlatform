"""向量化 —— **落库后异步补向量** ✓（C5）。

依据：Memory 方案 §5.4（C5 向量化 ✓）、§10.1（A2 ``vectorize.py`` ✓）。

⚠️ **写路径不再内联 embedding 调用** ✓（§5.4 的目标 ✓）—— 落库成功后
**排进队列** ✓，由后台 worker 补写向量 ✓（不阻塞对话 ✓）。

⚠️ **embedding 不可用 ≠ 写入失败** ✓（§5.4 的降级口径 ✓）—— 记忆**照常
落库** ✓（向量缺失只影响召回质量 ✓）→ **由补写兜底** ✓（`backfill` ✓）。

⚠️ **删除要同步删向量** ✓（§5.4 ✓）—— 否则向量成为**残留副本** ✓✗
（同一份内容还留在向量库里 ✗✗ —— 治理域的「删干净」就做不到 ✓）。

⚠️ **这一层是契约层** —— 端口 + 编排 ✓（embedding / 向量库的实现归模块侧 ✓）。
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Protocol, runtime_checkable
from uuid import UUID

from qzdap_observability.metrics import record_memory_vector_enqueue

_log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class VectorWriteRequest:
    """一条**待补写**的向量 ✓（§5.4 ✓）。"""

    tenant_id: UUID
    workspace_id: UUID
    item_id: UUID
    layer: str
    content: str
    user_id: UUID | None = None
    session_id: UUID | None = None


@runtime_checkable
class VectorWritePort(Protocol):
    """向量的写入 / 删除 ✓（实现在模块侧 ✓ —— embedding 与向量库在那儿 ✓）。"""

    async def upsert(self, request: VectorWriteRequest) -> None:
        """补写一条向量 ✓（**失败要抛** ✓ —— 由 worker 重试 ✓）。"""
        ...

    async def delete(self, item_ids: tuple[UUID, ...]) -> None:
        """删向量 ✓（**删 L2 时同步删** ✓ —— 不留残留副本 ✓）。"""
        ...


@runtime_checkable
class VectorWriteQueuePort(Protocol):
    """向量补写的**队列** ✓（实现归模块侧 / 组合根 ✓）。"""

    def enqueue(self, request: VectorWriteRequest) -> None:
        """**排一条** ✓ —— **不等** ✓（不阻塞对话 ✓）。"""
        ...


@runtime_checkable
class VectorBackfillPort(Protocol):
    """**兜底补写**的来源 ✓（实现在模块侧 ✓ —— 它要查库 ✓）。"""

    async def find_missing(self, *, limit: int) -> list[VectorWriteRequest]:
        """找出**该补向量**的条目 ✓（返回空列表 = 没有要补的 ✓）。

        ⚠️ **跨租户扫描** ✓ —— 它是**维护任务** ✓（不是请求路径 ✓）。
        """
        ...


class InMemoryVectorWriteQueue:
    """**进程内**的向量补写队列 ✓（§5.4 ✓）。

    ⚠️ **满了就丢** ✓ —— 不阻塞对话 ✓（宁可丢一条向量 ✓ —— 也别把对话
    卡住 ✗✗）；**丢掉的会被兜底补写捡回来** ✓（`backfill` ✓）。
    """

    def __init__(self, *, maxsize: int = 1000) -> None:
        self._queue: asyncio.Queue[VectorWriteRequest] = asyncio.Queue(maxsize=maxsize)
        self._maxsize = maxsize
        self.dropped = 0

    def enqueue(self, request: VectorWriteRequest) -> None:
        """排一条 ✓ —— **满了就丢** ✓（并计数 ✓ —— 丢了要看得见 ✓）。"""
        try:
            self._queue.put_nowait(request)
        except asyncio.QueueFull:
            self.dropped += 1
            record_memory_vector_enqueue(dropped=True)
            return
        record_memory_vector_enqueue(dropped=False)

    async def get(self) -> VectorWriteRequest | None:
        """取一条 ✓ —— **没有就返回 None** ✓（不是阻塞等待 ✓）。"""
        try:
            return self._queue.get_nowait()
        except asyncio.QueueEmpty:
            return None

    def __len__(self) -> int:
        return self._queue.qsize()

    @property
    def maxsize(self) -> int:
        return self._maxsize


class VectorizeWorker:
    """**后台补写向量** ✓（§5.4 ✓）。

    ⚠️ **失败要重试** ✓ —— embedding 服务抖一下不该让向量永远缺着 ✓；
    ⚠️ **重试有上限** ✓ —— 一直失败就**留给兜底补写** ✓（不无限重试 ✗✗）。
    """

    def __init__(
        self,
        *,
        queue: VectorWriteQueuePort,
        store: VectorWritePort,
        backfill: VectorBackfillPort | None = None,
        batch_size: int = 20,
        max_attempts: int = 3,
    ) -> None:
        self._queue = queue
        self._store = store
        self._backfill = backfill
        self._batch_size = max(1, batch_size)
        self._max_attempts = max(1, max_attempts)

    async def drain_once(self) -> int:
        """补一批 ✓ —— 返回**补成功几条** ✓。"""
        written = 0
        for _ in range(self._batch_size):
            request = await self._get()
            if request is None:
                break
            if await self._write(request):
                written += 1
        return written

    async def _get(self) -> VectorWriteRequest | None:
        getter = getattr(self._queue, "get", None)
        if getter is None:
            return None
        return await getter()

    async def _write(self, request: VectorWriteRequest) -> bool:
        for attempt in range(self._max_attempts):
            try:
                await self._store.upsert(request)
                return True
            except Exception:
                if attempt + 1 >= self._max_attempts:
                    # ⚠️ **补不上就留给兜底补写** ✓（不无限重试 ✗✗）。
                    return False
                await asyncio.sleep(0.05 * (attempt + 1))
        return False

    async def backfill_once(self, *, limit: int = 100) -> int:
        """**兜底补写** ✓（§5.4 ✓）—— 把漏掉的重新排进队列 ✓。

        ⚠️ **没有来源就什么都不做** ✓（不猜 ✓）。
        """
        if self._backfill is None:
            return 0
        requests = await self._backfill.find_missing(limit=limit)
        for request in requests:
            self._queue.enqueue(request)
        return len(requests)

    async def run(self, *, interval_s: float = 30.0, backfill_every: int = 20) -> None:
        """**后台循环** ✓（由组合根起停 ✓ —— 与 sweeper 同类 ✓）。

        ⚠️ **每 ``backfill_every`` 轮做一次兜底补写** ✓ —— 丢掉的向量
        最终会被捡回来 ✓（§5.4 ✓ —— 「由 C10 兜底补写」✓）。
        """
        ticks = 0
        while True:
            try:
                await self.drain_once()
                ticks += 1
                if ticks % max(1, backfill_every) == 0:
                    await self.backfill_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                # ⚠️ **worker 崩了不能带崩进程** ✓ —— 下一轮继续 ✓（但要留痕 ✓）。
                _log.warning("memory_vector_worker_iteration_failed", exc_info=True)
            await asyncio.sleep(interval_s)


__all__ = [
    "InMemoryVectorWriteQueue",
    "VectorBackfillPort",
    "VectorWritePort",
    "VectorWriteQueuePort",
    "VectorWriteRequest",
    "VectorizeWorker",
]
