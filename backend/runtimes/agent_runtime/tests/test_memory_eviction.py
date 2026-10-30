"""Memory Stage 6：**C4 保留与淘汰** ✓（Memory 方案 §6 ✓）。

验收覆盖 ✓：

- **TTL 到期 → 置 retired** ✓（**不物理删** ✓ —— 保留审计 ✓）；
- **超出条数上限 → 淘汰最久没用的** ✓（LRU ✓）；
- **超出容量上限 → 继续淘汰** ✓；
- **向量同步删** ✓（不留残留副本 ✓）；
- **没到上限 → 不动** ✓。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from qzdap_agent_runtime.memory.eviction import (
    EvictionCandidate,
    EvictionPolicy,
    Evictor,
)


class _Store:
    def __init__(self, candidates: list[EvictionCandidate] | None = None) -> None:
        self.candidates = candidates or []
        self.retired: tuple = ()
        self.deleted_vectors: tuple = ()

    async def list_candidates(self, *, workspace_id, layer):  # type: ignore[no-untyped-def]
        return list(self.candidates)

    async def retire(self, *, workspace_id, item_ids) -> None:  # type: ignore[no-untyped-def]
        self.retired = item_ids

    async def delete_vectors(self, item_ids) -> None:  # type: ignore[no-untyped-def]
        self.deleted_vectors = item_ids


def _candidate(*, age_days: float = 0.0, used: bool = True, size: int = 100) -> EvictionCandidate:
    now = datetime.now(UTC)
    stamp = now - timedelta(days=age_days)
    return EvictionCandidate(
        id=uuid4(),
        content_bytes=size,
        updated_at=stamp,
        last_used_at=stamp if used else None,
        used_count=1 if used else 0,
    )


class TestTheEvictor:
    @pytest.mark.asyncio
    async def test_expired_rows_are_retired(self) -> None:
        """**TTL 到期 → 置 retired** ✓（不物理删 ✓）。"""
        old = _candidate(age_days=10)
        fresh = _candidate(age_days=0)
        store = _Store([old, fresh])
        evictor = Evictor(store=store)
        report = await evictor.evict(
            workspace_id=uuid4(),
            policy=EvictionPolicy(ttl_minutes=60),
            now=datetime.now(UTC),
        )
        assert report.retired == 1
        assert report.by_ttl == 1
        assert store.retired == (old.id,)
        # ⚠️ **向量同步删** ✓。
        assert store.deleted_vectors == (old.id,)

    @pytest.mark.asyncio
    async def test_the_least_recently_used_goes_first(self) -> None:
        """**超出条数上限 → 最久没用的先走** ✓（LRU ✓）。"""
        oldest = _candidate(age_days=9)
        middle = _candidate(age_days=5)
        newest = _candidate(age_days=0)
        store = _Store([oldest, middle, newest])
        evictor = Evictor(store=store)
        report = await evictor.evict(
            workspace_id=uuid4(),
            policy=EvictionPolicy(max_items=1),
            now=datetime.now(UTC),
        )
        assert report.by_max_items == 2
        assert set(store.retired) == {oldest.id, middle.id}
        assert newest.id not in store.retired

    @pytest.mark.asyncio
    async def test_the_storage_limit_evicts_more(self) -> None:
        """**超出容量上限 → 继续淘汰** ✓。"""
        big = _candidate(age_days=9, size=1024 * 1024)
        small = _candidate(age_days=0, size=1024)
        store = _Store([big, small])
        evictor = Evictor(store=store)
        report = await evictor.evict(
            workspace_id=uuid4(),
            policy=EvictionPolicy(storage_mb=1),
            now=datetime.now(UTC),
        )
        assert report.by_storage >= 1
        assert big.id in store.retired

    @pytest.mark.asyncio
    async def test_nothing_happens_below_the_limits(self) -> None:
        """**没到上限 → 不动** ✓。"""
        store = _Store([_candidate()])
        evictor = Evictor(store=store)
        report = await evictor.evict(
            workspace_id=uuid4(),
            policy=EvictionPolicy(ttl_minutes=60, max_items=10, storage_mb=10),
            now=datetime.now(UTC),
        )
        assert report.retired == 0
        assert report.kept == 1
        assert store.retired == ()

    @pytest.mark.asyncio
    async def test_an_empty_layer_is_a_no_op(self) -> None:
        """**没有候选 → 什么都不做** ✓。"""
        store = _Store([])
        evictor = Evictor(store=store)
        report = await evictor.evict(
            workspace_id=UUID(int=1),
            policy=EvictionPolicy(ttl_minutes=1),
            now=datetime.now(UTC),
        )
        assert report.total == 0
