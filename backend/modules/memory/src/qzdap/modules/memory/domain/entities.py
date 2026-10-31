"""Admin memory aggregates — fields match frontend `features/memory/schema.ts`."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal, Self
from uuid import UUID, uuid4

EMBEDDING_DIM = 1536

#: ⚠️ **只有 L2 了** ✓ —— L1 退役（决策 #5 ✓ —— M-46 ✓）、
#: L3 退役（决策 #1 ✓ —— M-47 ✓）→ 记忆的用户级那一层 ✓。
MemoryLayer = Literal["l2"]
L2Status = Literal["pending", "confirmed", "retired"]
L2Category = Literal["preference", "fact", "style", "context"]
EvictionStrategy = Literal["lru", "fifo", "confidence"]
#: ⚠️ **提升的终点是 knowledge** ✓ —— 不再有 L3 ✓（决策 #1 ✓ —— M-47 ✓）。
PromotionLayer = Literal["l1→l2", "l2→knowledge"]

L2_STATUSES = frozenset({"pending", "confirmed", "retired"})
L2_CATEGORIES = frozenset({"preference", "fact", "style", "context"})
EVICTIONS = frozenset({"lru", "fifo", "confidence"})
LAYERS = frozenset({"l2"})


def _utcnow() -> datetime:
    return datetime.now(UTC)


def format_last_update(moment: datetime) -> str:
    now = _utcnow()
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    seconds = max(0, (now - moment).total_seconds())
    if seconds < 120:
        return "刚刚"
    if seconds < 3600:
        return f"{int(seconds // 60)} 分钟前"
    if seconds < 86400:
        return f"{int(seconds // 3600)} 小时前"
    if seconds < 86400 * 7:
        return f"{int(seconds // 86400)} 天前"
    return moment.astimezone(UTC).strftime("%Y-%m-%d %H:%M")


@dataclass(slots=True)
class L2Fact:
    id: UUID
    tenant_id: UUID
    workspace_id: UUID
    user_name: str
    key: str
    value: str
    category: L2Category
    source_session: str
    confidence: float
    status: L2Status
    promoted_to_l3: bool
    updated_at: datetime
    created_at: datetime
    usage_history: list[str] = field(default_factory=list)
    # 归属用户（决策 #11）。None = 归属不明（存量自动沉淀的记忆）——
    # 这类行在用户级作用域过滤下**不可见**，宁可不可见也不能串号。
    user_id: UUID | None = None
    # ── 以下字段对应迁移 0048 已建的列 ✓（去重 / 追溯 / 统计 ✓）──
    #: 内容哈希 ✓（去重用 ✓ —— §4.4 ✓）；**存量行是 None** ✓（存量不参与去重 ✓）
    content_hash: str | None = None
    #: 哈希的规范化规则版本 ✓（§4.4 ✓）
    content_hash_version: int = 1
    #: 来源轮次 ✓（可追溯 ✓ —— §4.1 ✓）
    source_turn_id: UUID | None = None
    #: 最后一次被用到的时刻 ✓（统计 ✓）
    last_used_at: datetime | None = None
    #: 被用过多少次 ✓（统计 ✓ —— §3.5 ✓）
    used_count: int = 0
    #: 置信度来源 ✓（`explicit` / `rule` / `llm` ✓ —— §4.5 ✓）
    confidence_source: str = "rule"
    #: 版本 ✓（召回要带出去 ✓ —— Context manifest 用 ✓）
    version: int = 1

    def recall_text(self) -> str:
        return f"{self.key}: {self.value}".strip()

    def to_admin_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "id": str(self.id),
            "userName": self.user_name,
            "userId": str(self.user_id) if self.user_id else None,
            "key": self.key,
            "value": self.value,
            "category": self.category,
            "sourceSession": self.source_session,
            "confidence": self.confidence,
            "lastUsed": format_last_update(self.updated_at),
            "promotedAt": format_last_update(self.created_at),
            "status": self.status,
            "promotedToL3": self.promoted_to_l3,
            # ⚠️ **版本号** ✓（乐观并发 ✓ —— 决策 #10 ✓）—— 管理端编辑要带它
            # （不带 = 后写覆盖 ✗✗）。
            "version": int(self.version or 1),
        }
        if self.usage_history:
            out["usageHistory"] = list(self.usage_history)
        return out


@dataclass(slots=True)
class PromotionEvent:
    id: UUID
    tenant_id: UUID
    workspace_id: UUID
    layer: PromotionLayer
    label: str
    operator: str
    target_id: str
    created_at: datetime
    #: **从哪一层来** ✓（迁移 0048 建的列 ✓ —— M-30 ✓）。
    from_layer: str = "l1"
    #: **到哪一层去** ✓（迁移 0048 建的列 ✓ —— M-30 ✓）。
    to_layer: str = "l2"
    #: **为什么提升** ✓（迁移 0048 建的列 ✓ —— M-30 ✓）。
    reason: str = ""

    def to_admin_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "layer": self.layer,
            "label": self.label,
            "at": format_last_update(self.created_at),
            "operator": self.operator,
            "targetId": self.target_id,
            "fromLayer": self.from_layer,
            "toLayer": self.to_layer,
            "reason": self.reason,
        }


@dataclass(slots=True)
class RetentionPolicy:
    id: UUID
    tenant_id: UUID
    workspace_id: UUID
    layer: MemoryLayer
    label: str
    description: str
    ttl_minutes: int
    max_items: int
    storage_mb: int
    eviction: EvictionStrategy
    hit_rate: float
    updated_at: datetime
    created_at: datetime

    def to_admin_dict(self) -> dict[str, Any]:
        return {
            "layer": self.layer,
            "label": self.label,
            "description": self.description,
            "ttlMinutes": self.ttl_minutes,
            "maxItems": self.max_items,
            "storageMb": self.storage_mb,
            "eviction": self.eviction,
            "hitRate": self.hit_rate,
        }

    @classmethod
    def defaults(cls, *, tenant_id: UUID, workspace_id: UUID) -> list[Self]:
        now = _utcnow()
        # ⚠️ **只有 L2** ✓ —— 「短期记忆」（L1 ✓ —— M-46 ✓ 已退役）与
        # 「知识记忆」（L3 ✓ —— M-47 ✓ 已退役）都没有了 ✓。
        specs: list[tuple[MemoryLayer, str, str, int, int, int, EvictionStrategy, float]] = [
            ("l2", "长期记忆", "用户偏好与事实", 60 * 24 * 90, 200, 32, "lru", 0.88),
        ]

        return [
            cls(
                id=uuid4(),
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                layer=layer,
                label=label,
                description=description,
                ttl_minutes=ttl,
                max_items=max_items,
                storage_mb=storage,
                eviction=eviction,
                hit_rate=hit_rate,
                updated_at=now,
                created_at=now,
            )
            for layer, label, description, ttl, max_items, storage, eviction, hit_rate in specs
        ]


__all__ = [
    "EMBEDDING_DIM",
    "L2Fact",
    "PromotionEvent",
    "RetentionPolicy",
    "format_last_update",
]
