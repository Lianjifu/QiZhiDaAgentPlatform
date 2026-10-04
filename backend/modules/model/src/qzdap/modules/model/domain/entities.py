"""Admin model catalog — fields match frontend `features/models/schema.ts`."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Any, Literal, Self
from uuid import UUID

ModelStatus = Literal["active", "graying", "draft", "retired"]
ProviderStatus = Literal["healthy", "degraded", "down"]
RouteStrategy = Literal["quality-first", "cost-first", "latency-first", "fallback"]
TaskType = Literal["reasoning", "generation", "classification", "embedding", "summarization"]
ModelTier = Literal["premium", "balanced", "economy"]
HealthEventType = Literal["incident", "latency", "quota", "recovery"]
ModelProtocol = Literal["openai", "azure", "anthropic", "openai-compatible"]

MODEL_STATUSES = frozenset({"active", "graying", "draft", "retired"})
PROVIDER_STATUSES = frozenset({"healthy", "degraded", "down"})
ROUTE_STRATEGIES = frozenset({"quality-first", "cost-first", "latency-first", "fallback"})
TASK_TYPES = frozenset({"reasoning", "generation", "classification", "embedding", "summarization"})
MODEL_TIERS = frozenset({"premium", "balanced", "economy"})
HEALTH_TYPES = frozenset({"incident", "latency", "quota", "recovery"})
PROTOCOLS = frozenset({"openai", "azure", "anthropic", "openai-compatible"})

FALLBACK_CATALOG: dict[str, list[str]] = {
    "openai": ["gpt-4o", "gpt-4o-mini", "o1-preview", "text-embedding-3-large"],
    "azure": ["gpt-4o", "gpt-35-turbo", "text-embedding-3"],
    "anthropic": ["claude-3-5-sonnet", "claude-3-5-haiku", "claude-3-opus"],
    "openai-compatible": ["llama-3.1-70b", "qwen-max", "deepseek-chat"],
}


def _utcnow() -> datetime:
    return datetime.now(UTC)


def infer_tasks(name: str) -> list[TaskType]:
    lower = name.lower()
    if "embed" in lower:
        return ["embedding"]
    if "o1" in lower or "reason" in lower:
        return ["reasoning"]
    return ["generation"]


def mask_api_key(api_key: str) -> str:
    tail = api_key.strip()[-4:] if api_key.strip() else ""
    return f"••••{tail}" if tail else "••••"


@dataclass(slots=True)
class Provider:
    id: UUID
    tenant_id: UUID
    workspace_id: UUID
    name: str
    region: str
    status: ProviderStatus
    base_url: str
    api_key_masked: str
    protocol: ModelProtocol
    encrypted_payload: bytes
    error_rate: float
    avg_latency_ms: int
    qps: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def create(
        cls,
        *,
        id: UUID,
        tenant_id: UUID,
        workspace_id: UUID,
        name: str,
        base_url: str,
        protocol: ModelProtocol,
        api_key_masked: str,
        encrypted_payload: bytes = b"",
        region: str = "custom",
    ) -> Self:
        now = _utcnow()
        proto: ModelProtocol = protocol if protocol in PROTOCOLS else "openai-compatible"
        return cls(
            id=id,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            name=name.strip() or "未命名提供商",
            region=region,
            status="healthy",
            base_url=base_url.strip(),
            api_key_masked=api_key_masked,
            protocol=proto,
            encrypted_payload=encrypted_payload,
            error_rate=0,
            avg_latency_ms=0,
            qps=0,
            created_at=now,
            updated_at=now,
        )

    def to_admin_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "name": self.name,
            "region": self.region,
            "status": self.status,
            "baseUrl": self.base_url,
            "apiKeyMasked": self.api_key_masked,
            "protocol": self.protocol,
            "errorRate": self.error_rate,
            "avgLatencyMs": self.avg_latency_ms,
            "qps": self.qps,
        }


@dataclass(slots=True)
class Model:
    id: UUID
    tenant_id: UUID
    workspace_id: UUID
    name: str
    provider_id: UUID
    provider_name: str
    task: list[TaskType]
    context_window: int
    price_in: float
    price_out: float
    latency_ms: int
    success_rate: float
    status: ModelStatus
    tier: ModelTier
    starred: bool
    calls: int
    trend: list[int]
    description: str
    tags: list[str]
    created_at: datetime
    updated_at: datetime

    @classmethod
    def create(
        cls,
        *,
        id: UUID,
        tenant_id: UUID,
        workspace_id: UUID,
        name: str,
        provider_id: UUID,
        provider_name: str,
        protocol: str,
    ) -> Self:
        now = _utcnow()
        return cls(
            id=id,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            name=name.strip(),
            provider_id=provider_id,
            provider_name=provider_name,
            task=infer_tasks(name),
            context_window=128000,
            price_in=0,
            price_out=0,
            latency_ms=0,
            success_rate=0,
            status="draft",
            tier="balanced",
            starred=False,
            calls=0,
            trend=[0] * 12,
            description=f"经 {provider_name}（{protocol}）接入",
            tags=[protocol],
            created_at=now,
            updated_at=now,
        )

    def apply_patch(self, patch: dict[str, Any]) -> Self:
        data: dict[str, Any] = {}
        if patch.get("name"):
            data["name"] = str(patch["name"]).strip()
        if "description" in patch:
            data["description"] = str(patch["description"])
        if "status" in patch and patch["status"] in MODEL_STATUSES:
            data["status"] = patch["status"]
        if "tier" in patch and patch["tier"] in MODEL_TIERS:
            data["tier"] = patch["tier"]
        if "starred" in patch:
            data["starred"] = bool(patch["starred"])
        if "contextWindow" in patch:
            data["context_window"] = int(patch["contextWindow"] or 0)
        if "priceIn" in patch:
            data["price_in"] = float(patch["priceIn"] or 0)
        if "priceOut" in patch:
            data["price_out"] = float(patch["priceOut"] or 0)
        if "task" in patch and isinstance(patch["task"], list):
            data["task"] = [item for item in patch["task"] if item in TASK_TYPES] or list(self.task)
        if "tags" in patch and isinstance(patch["tags"], list):
            data["tags"] = [str(item) for item in patch["tags"]]
        data["updated_at"] = _utcnow()
        return replace(self, **data)

    def with_starred(self, starred: bool) -> Self:
        return replace(self, starred=starred, updated_at=_utcnow())

    def with_status(self, status: ModelStatus) -> Self:
        return replace(self, status=status, updated_at=_utcnow())

    def record_call(self, *, latency_ms: int, ok: bool) -> Self:
        trend = list(self.trend or [0] * 12)
        if len(trend) < 12:
            trend = ([0] * (12 - len(trend))) + trend
        trend = trend[1:] + [trend[-1] + 1]
        calls = self.calls + 1
        success = self.success_rate
        if calls > 0:
            prev_ok = success / 100.0 * (calls - 1)
            success = round(((prev_ok + (1 if ok else 0)) / calls) * 100, 1)
        avg = latency_ms if self.latency_ms == 0 else int((self.latency_ms * (calls - 1) + latency_ms) / calls)
        return replace(
            self,
            calls=calls,
            trend=trend[-12:],
            success_rate=success,
            latency_ms=avg,
            updated_at=_utcnow(),
        )

    def to_admin_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "name": self.name,
            "providerId": str(self.provider_id),
            "providerName": self.provider_name,
            "task": list(self.task),
            "contextWindow": self.context_window,
            "priceIn": self.price_in,
            "priceOut": self.price_out,
            "latencyMs": self.latency_ms,
            "successRate": self.success_rate,
            "status": self.status,
            "tier": self.tier,
            "starred": self.starred,
            "calls": self.calls,
            "trend": list(self.trend),
            "description": self.description,
            "tags": list(self.tags),
        }


@dataclass(slots=True)
class RouteRule:
    id: UUID
    tenant_id: UUID
    workspace_id: UUID
    name: str
    task: TaskType
    strategy: RouteStrategy
    priority: int
    primary_model_id: UUID
    fallback_model_ids: list[str]
    enabled: bool
    description: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def create(
        cls,
        *,
        id: UUID,
        tenant_id: UUID,
        workspace_id: UUID,
        name: str,
        task: TaskType,
        strategy: RouteStrategy,
        priority: int,
        primary_model_id: UUID,
        description: str,
    ) -> Self:
        now = _utcnow()
        return cls(
            id=id,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            name=name.strip() or "未命名路由",
            task=task if task in TASK_TYPES else "generation",
            strategy=strategy if strategy in ROUTE_STRATEGIES else "quality-first",
            priority=int(priority),
            primary_model_id=primary_model_id,
            fallback_model_ids=[],
            enabled=True,
            description=description or "",
            created_at=now,
            updated_at=now,
        )

    def toggled(self) -> Self:
        return replace(self, enabled=not self.enabled, updated_at=_utcnow())

    def to_admin_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "name": self.name,
            "task": self.task,
            "strategy": self.strategy,
            "priority": self.priority,
            "primaryModelId": str(self.primary_model_id),
            "fallbackModelIds": list(self.fallback_model_ids),
            "enabled": self.enabled,
            "description": self.description,
        }


@dataclass(slots=True)
class HealthEvent:
    id: UUID
    tenant_id: UUID
    workspace_id: UUID
    type: HealthEventType
    provider_id: UUID
    provider_name: str
    message: str
    occurred_at: str
    created_at: datetime = field(default_factory=_utcnow)

    def to_admin_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "type": self.type,
            "providerId": str(self.provider_id),
            "providerName": self.provider_name,
            "message": self.message,
            "occurredAt": self.occurred_at,
        }


__all__ = [
    "FALLBACK_CATALOG",
    "HealthEvent",
    "Model",
    "Provider",
    "RouteRule",
    "infer_tasks",
    "mask_api_key",
]
