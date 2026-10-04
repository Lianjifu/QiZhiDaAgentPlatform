"""Pydantic v2 DTOs for the evaluation HTTP surface.

Strict models with ``ConfigDict(extra="forbid")`` so a typo in a client
request is rejected at the boundary instead of silently dropped.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DatasetResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    tenant_id: UUID
    workspace_id: UUID
    name: str
    description: str
    kind: str
    status: str
    case_count: int
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_by: UUID | None
    created_at: datetime
    updated_at: datetime


class DatasetListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[DatasetResponse]
    count: int


class CaseResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    tenant_id: UUID
    workspace_id: UUID
    dataset_id: UUID
    ordinal: int
    input: str
    expected_keywords: tuple[str, ...]
    min_keywords_hit_ratio: float
    max_latency_ms: int
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class CaseListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[CaseResponse]
    count: int


class RunResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    tenant_id: UUID
    workspace_id: UUID
    dataset_id: UUID
    template_id: UUID
    version_id: UUID
    status: str
    mean_score: float | None
    case_count: int
    passed_count: int
    failed_count: int
    started_at: datetime | None
    completed_at: datetime | None
    error_message: str | None
    idempotency_key: str | None
    triggered_by: UUID | None
    created_at: datetime
    updated_at: datetime


class RunListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[RunResponse]
    count: int


class StartRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    template_id: UUID
    version_id: UUID
    dataset_id: UUID
    idempotency_key: str | None = Field(default=None, max_length=128)


__all__ = [
    "CaseListResponse",
    "CaseResponse",
    "DatasetListResponse",
    "DatasetResponse",
    "RunListResponse",
    "RunResponse",
    "StartRunRequest",
]
