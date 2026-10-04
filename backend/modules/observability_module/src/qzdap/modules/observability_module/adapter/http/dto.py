"""HTTP DTOs for the observability module."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ── RunRecord ─────────────────────────────────────────────────────────────


class RunRecordResponse(_StrictModel):
    id: str
    tenant_id: str
    workspace_id: str
    run_type: str
    source_id: str | None
    actor_id: str | None
    started_at: str | None
    completed_at: str
    latency_ms: int | None
    status: str
    metadata: dict[str, Any]
    created_at: str


class RunRecordListResponse(_StrictModel):
    items: list[RunRecordResponse]
    count: int


# ── CostRecord / aggregate ────────────────────────────────────────────────


class CostRecordResponse(_StrictModel):
    id: str
    tenant_id: str
    workspace_id: str
    run_id: str
    cost_type: str
    amount_usd: str  # Decimal serialized as string
    quantity: int | None
    unit: str
    currency: str
    model_id: str | None
    metadata: dict[str, Any]
    created_at: str


class CostRecordListResponse(_StrictModel):
    items: list[CostRecordResponse]
    count: int


class CostAggregateItem(_StrictModel):
    # group_by="cost_type" → cost_type is set, others null
    cost_type: str | None = None
    # group_by="workspace" → workspace_id is set
    workspace_id: str | None = None
    # group_by="model" → model_id is set
    model_id: str | None = None
    total_usd: str


class CostAggregateResponse(_StrictModel):
    group_by: str = Field(description="cost_type | workspace | model")
    items: list[CostAggregateItem]
    count: int


# ── QualityScore ──────────────────────────────────────────────────────────


class QualityScoreResponse(_StrictModel):
    template_id: str
    version_id: str
    latest_eval_run_id: str | None
    mean_score: float
    sample_count: int
    completed_at: str | None


__all__ = [
    "CostAggregateItem",
    "CostAggregateResponse",
    "CostRecordListResponse",
    "CostRecordResponse",
    "QualityScoreResponse",
    "RunRecordListResponse",
    "RunRecordResponse",
]
