"""**保留与淘汰** ✓（C4 —— Memory 方案 §6 ✓）。

⚠️ **策略第一次有执行者** ✓（§1.6 的问题 ✓）—— `admin_memory_policies` 的
``ttl_minutes`` / ``max_items`` / ``storage_mb`` / ``eviction`` 不再是死数据 ✓。

⚠️ **淘汰 = 置 ``retired``** ✓（**不物理删** ✓ —— 保留审计 ✓ —— §6 ✓）——
⚠️ **不要引入 ``expired`` / ``active`` 这两套新词** ✓（§9.1.1 ✓）——
CAS 只能用 ``status='confirmed'`` ✓。

⚠️ **删向量要同步** ✓（§5.4 ✓）—— 否则向量成为**残留副本** ✓✗。

⚠️ **这一层是契约层** —— 规则 + 编排 ✓（落库归模块侧 ✓）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Protocol, runtime_checkable
from uuid import UUID

from qzdap_observability.metrics import record_memory_eviction


@dataclass(frozen=True, slots=True)
class EvictionPolicy:
    """一条**保留策略** ✓（§6 ✓ —— 与 ``admin_memory_policies`` 同口径 ✓）。"""

    layer: str = "l2"
    label: str = ""
    ttl_minutes: int = 0
    max_items: int = 0
    storage_mb: int = 0
    eviction: str = "lru"

    @property
    def ttl(self) -> timedelta | None:
        """**TTL** ✓（0 = 不限 ✓）。"""
        if self.ttl_minutes <= 0:
            return None
        return timedelta(minutes=self.ttl_minutes)


@dataclass(frozen=True, slots=True)
class EvictionCandidate:
    """一条**待判定**的记忆 ✓。"""

    id: UUID
    content_bytes: int = 0
    updated_at: datetime | None = None
    last_used_at: datetime | None = None
    used_count: int = 0


@dataclass(frozen=True, slots=True)
class EvictionReport:
    """一次淘汰的结果 ✓。"""

    #: **被置 retired 的** 条数 ✓。
    retired: int = 0
    #: **因为 TTL 到期** 的条数 ✓。
    by_ttl: int = 0
    #: **因为超出条数上限** 的条数 ✓。
    by_max_items: int = 0
    #: **因为超出容量上限** 的条数 ✓。
    by_storage: int = 0
    #: **被删的向量** 条数 ✓（同步删 ✓）。
    vectors_deleted: int = 0
    #: **被判定但没动** 的条数 ✓（还在用 ✓）。
    kept: int = 0
    #: 逐条原因 ✓（审计 / 排障 ✓）。
    details: list[dict] = field(default_factory=list)

    @property
    def total(self) -> int:
        return self.retired


@runtime_checkable
class EvictionPort(Protocol):
    """**淘汰要用的存储能力** ✓（实现在模块侧 ✓ —— 它要碰库 ✓）。"""

    async def list_candidates(
        self, *, workspace_id: UUID, layer: str
    ) -> list[EvictionCandidate]:
        """**候选** ✓（确认状态的 ✓ —— 只处理活着的 ✓）。"""
        ...

    async def retire(self, *, workspace_id: UUID, item_ids: tuple[UUID, ...]) -> None:
        """**置 retired** ✓（不物理删 ✓ —— 保留审计 ✓）。"""
        ...

    async def delete_vectors(self, item_ids: tuple[UUID, ...]) -> None:
        """**同步删向量** ✓（不留残留副本 ✓）。"""
        ...


class Evictor:
    """**淘汰器** ✓（§6 ✓）。

    ⚠️ **三条规则按这个顺序** ✓：TTL → 条数上限 → 容量上限 ✓
    （先按时间清 ✓ —— 剩下的再按压力清 ✓）。
    """

    def __init__(self, *, store: EvictionPort) -> None:
        self._store = store

    async def evict(
        self, *, workspace_id: UUID, policy: EvictionPolicy, now: datetime
    ) -> EvictionReport:
        """**按策略淘汰** ✓。"""
        candidates = await self._store.list_candidates(
            workspace_id=workspace_id, layer=policy.layer
        )
        if not candidates:
            return EvictionReport()
        victims: dict[UUID, str] = {}

        # ── ① TTL ✓ ────────────────────────────────────────────────
        ttl = policy.ttl
        if ttl is not None:
            for candidate in candidates:
                stamp = candidate.last_used_at or candidate.updated_at
                if stamp is None:
                    continue
                if now - stamp > ttl:
                    victims[candidate.id] = "ttl"

        # ── ② 条数上限 ✓（LRU：最久没用���先走 ✓）────────────────────
        survivors = [c for c in candidates if c.id not in victims]
        if policy.max_items > 0 and len(survivors) > policy.max_items:
            survivors.sort(key=_lru_key)
            for candidate in survivors[: len(survivors) - policy.max_items]:
                victims[candidate.id] = "max_items"

        # ── ③ 容量上限 ✓（按内容字节估算 ✓）────────────────────────
        survivors = [c for c in candidates if c.id not in victims]
        if policy.storage_mb > 0:
            limit = policy.storage_mb * 1024 * 1024
            total = sum(c.content_bytes for c in survivors)
            while total > limit and survivors:
                survivors.sort(key=_lru_key)
                candidate = survivors.pop(0)
                victims[candidate.id] = "storage"
                total -= candidate.content_bytes

        if not victims:
            return EvictionReport(kept=len(candidates))

        await self._store.retire(
            workspace_id=workspace_id, item_ids=tuple(victims)
        )
        await self._store.delete_vectors(tuple(victims))
        by_ttl = sum(1 for reason in victims.values() if reason == "ttl")
        by_max = sum(1 for reason in victims.values() if reason == "max_items")
        by_storage = sum(1 for reason in victims.values() if reason == "storage")
        # ⚠️ **按原因计数** ✓（Memory 方案 §14.2 ✓ —— 才知道哪条规则在起作用 ✓）。
        record_memory_eviction(reason="ttl", count=by_ttl)
        record_memory_eviction(reason="max_items", count=by_max)
        record_memory_eviction(reason="storage", count=by_storage)
        return EvictionReport(
            retired=len(victims),
            by_ttl=by_ttl,
            by_max_items=by_max,
            by_storage=by_storage,
            vectors_deleted=len(victims),
            kept=len(candidates) - len(victims),
            details=[
                {"id": str(item_id), "reason": reason}
                for item_id, reason in victims.items()
            ],
        )


def _lru_key(candidate: EvictionCandidate) -> tuple[datetime, int]:
    """**LRU 排序键** ✓ —— 最久没用过的先走 ✓。

    ⚠️ **没用过的排在用过的前面** ✓（``last_used_at`` 为空 ✓ —— 那些是
    「写了就没再被召回」的 ✓ —— 它们最该被淘汰 ✓）。
    """
    stamp = candidate.last_used_at or candidate.updated_at
    if stamp is None:
        return (datetime.min.replace(tzinfo=UTC), 0)
    return (stamp, candidate.used_count)


__all__ = [
    "EvictionCandidate",
    "EvictionPolicy",
    "EvictionPort",
    "EvictionReport",
    "Evictor",
]
