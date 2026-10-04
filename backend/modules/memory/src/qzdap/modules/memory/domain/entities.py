"""Admin memory aggregates — fields match frontend `features/memory/schema.ts`."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal, Self
from uuid import UUID

EMBEDDING_DIM = 1536

MemoryLayer = Literal["l1", "l2", "l3"]
L1Status = Literal["active", "paused", "expired"]
L2Status = Literal["pending", "confirmed", "retired"]
L3Status = Literal["draft", "published", "retired"]
L2Category = Literal["preference", "fact", "style", "context"]
EvictionStrategy = Literal["lru", "fifo", "confidence"]
PromotionLayer = Literal["l1→l2", "l2→l3"]

L1_STATUSES = frozenset({"active", "paused", "expired"})
L2_STATUSES = frozenset({"pending", "confirmed", "retired"})
L3_STATUSES = frozenset({"draft", "published", "retired"})
L2_CATEGORIES = frozenset({"preference", "fact", "style", "context"})
EVICTIONS = frozenset({"lru", "fifo", "confidence"})
LAYERS = frozenset({"l1", "l2", "l3"})


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
class L1Session:
    id: UUID
    tenant_id: UUID
    workspace_id: UUID
    user_name: str
    agent_name: str
    buffer_size: int
    tokens_used: int
    ttl_minutes: int
    ttl_remain_min: int
    status: L1Status
    updated_at: datetime
    created_at: datetime
    buffer_text: str = ""

    def to_admin_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "userName": self.user_name,
            "agentName": self.agent_name,
            "bufferSize": self.buffer_size,
            "tokensUsed": self.tokens_used,
            "ttlMinutes": self.ttl_minutes,
            "ttlRemainMin": self.ttl_remain_min,
            "status": self.status,
            "lastFlush": format_last_update(self.updated_at),
            "startedAt": format_last_update(self.created_at),
        }


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

    def recall_text(self) -> str:
        return f"{self.key}: {self.value}".strip()

    def to_admin_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "id": str(self.id),
            "userName": self.user_name,
            "key": self.key,
            "value": self.value,
            "category": self.category,
            "sourceSession": self.source_session,
            "confidence": self.confidence,
            "lastUsed": format_last_update(self.updated_at),
            "promotedAt": format_last_update(self.created_at),
            "status": self.status,
            "promotedToL3": self.promoted_to_l3,
        }
        if self.usage_history:
            out["usageHistory"] = list(self.usage_history)
        return out


@dataclass(slots=True)
class L3Entry:
    id: UUID
    tenant_id: UUID
    workspace_id: UUID
    team: str
    title: str
    summary: str
    category: str
    hits: int
    contributor: str
    status: L3Status
    updated_at: datetime
    created_at: datetime
    hits_trend: list[int] = field(default_factory=list)
    promoted_from_l2_ids: list[str] = field(default_factory=list)

    def recall_text(self) -> str:
        return f"{self.title}: {self.summary}".strip()

    def to_admin_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "id": str(self.id),
            "team": self.team,
            "title": self.title,
            "summary": self.summary,
            "category": self.category,
            "hits": self.hits,
            "updatedAt": format_last_update(self.updated_at),
            "contributor": self.contributor,
            "status": self.status,
        }
        if self.hits_trend:
            out["hitsTrend"] = list(self.hits_trend)
        if self.promoted_from_l2_ids:
            out["promotedFromL2Ids"] = list(self.promoted_from_l2_ids)
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

    def to_admin_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "layer": self.layer,
            "label": self.label,
            "at": format_last_update(self.created_at),
            "operator": self.operator,
            "targetId": self.target_id,
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
        specs: list[tuple[MemoryLayer, str, str, int, int, int, EvictionStrategy, float]] = [
            ("l1", "短期记忆", "会话上下文窗口", 60, 50, 8, "fifo", 0.94),
            ("l2", "长期记忆", "用户偏好与事实", 60 * 24 * 90, 200, 32, "lru", 0.88),
            ("l3", "知识记忆", "团队级共享知识", 60 * 24 * 365, 500, 128, "lru", 0.92),
        ]
        from uuid import uuid4

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
    "L1Session",
    "L2Fact",
    "L3Entry",
    "PromotionEvent",
    "RetentionPolicy",
    "format_last_update",
]
