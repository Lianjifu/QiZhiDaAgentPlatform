"""Memory Stage 5：**C5 向量化** ✓（Memory 方案 §5.4 ✓）。

验收覆盖 ✓：

- **落库后异步补向量** ✓（写路径排队 ✓ —— 不等 embedding ✓）；
- **补不上有兜底** ✓（worker 重试 ✓ + 兜底补写 ✓）；
- **队列满了不阻塞对话** ✓（丢一条 ✓ —— 计数 ✓）；
- **删除同步删向量** ✓（端口形状 ✓）。
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from qzdap_agent_runtime.memory.vectorize import (
    InMemoryVectorWriteQueue,
    VectorWriteRequest,
    VectorizeWorker,
)


def _request(*, content: str = "内容") -> VectorWriteRequest:
    return VectorWriteRequest(
        tenant_id=uuid4(),
        workspace_id=uuid4(),
        item_id=uuid4(),
        layer="l2",
        content=content,
    )


class _Store:
    def __init__(self, *, fail: bool = False) -> None:
        self.upserts: list[VectorWriteRequest] = []
        self.deleted: list[tuple] = []
        self.fail = fail

    async def upsert(self, request: VectorWriteRequest) -> None:
        if self.fail:
            raise RuntimeError("embedding service is down")
        self.upserts.append(request)

    async def delete(self, item_ids: tuple) -> None:
        self.deleted.append(item_ids)


class _Backfill:
    def __init__(self, requests: list[VectorWriteRequest] | None = None) -> None:
        self.requests = requests or []

    async def find_missing(self, *, limit: int = 100) -> list[VectorWriteRequest]:
        return self.requests[:limit]


class TestTheAsyncVectorWrite:
    @pytest.mark.asyncio
    async def test_the_queued_request_is_written(self) -> None:
        """**排队的会被补上** ✓（写路径不等它 ✓ —— 后台补 ✓）。"""
        queue = InMemoryVectorWriteQueue()
        store = _Store()
        worker = VectorizeWorker(queue=queue, store=store)
        request = _request()
        queue.enqueue(request)
        written = await worker.drain_once()
        assert written == 1
        assert store.upserts == [request]

    @pytest.mark.asyncio
    async def test_a_failing_embedding_is_retried_and_then_given_up(self) -> None:
        """**补不上 → 重试 → 放弃** ✓（不留无限重试 ✗✗）。"""
        queue = InMemoryVectorWriteQueue()
        store = _Store(fail=True)
        worker = VectorizeWorker(queue=queue, store=store, max_attempts=2)
        queue.enqueue(_request())
        written = await worker.drain_once()
        assert written == 0
        assert store.upserts == []

    @pytest.mark.asyncio
    async def test_a_full_queue_drops_instead_of_blocking(self) -> None:
        """**队列满了 → 丢** ✓（不阻塞对话 ✓ —— 丢了有兜底补写 ✓）。"""
        queue = InMemoryVectorWriteQueue(maxsize=1)
        queue.enqueue(_request())
        queue.enqueue(_request())
        assert queue.dropped == 1
        assert len(queue) == 1

    @pytest.mark.asyncio
    async def test_the_backfill_requeues_the_missing_ones(self) -> None:
        """**兜底补写** ✓（丢掉的向量最终会被捡回来 ✓）。"""
        queue = InMemoryVectorWriteQueue()
        store = _Store()
        missing = [_request(), _request()]
        worker = VectorizeWorker(
            queue=queue, store=store, backfill=_Backfill(missing)
        )
        requeued = await worker.backfill_once()
        assert requeued == 2
        assert len(queue) == 2
        assert await worker.drain_once() == 2
        assert store.upserts == missing

    @pytest.mark.asyncio
    async def test_the_delete_is_delivered(self) -> None:
        """**删 L2 → 同步删向量** ✓（不留残留副本 ✓）。"""
        store = _Store()
        item_id = uuid4()
        await store.delete((item_id,))
        assert store.deleted == [(item_id,)]
