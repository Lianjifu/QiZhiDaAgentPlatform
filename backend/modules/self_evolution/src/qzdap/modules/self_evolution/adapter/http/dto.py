"""Self-evolution HTTP DTOs — /v1/evolve/candidates/*."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from qzdap.modules.self_evolution.domain.value_objects import (
    EvolveKind,
    EvolveStatus,
)


class _BaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class CreateCandidateRequest(_BaseModel):
    kind: EvolveKind
    payload: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(ge=0.0, le=1.0)
    trigger_reason: str = Field(min_length=1, max_length=256)
    workspace_id: UUID | None = None
    ttl_seconds: int | None = Field(default=None, ge=1, le=86400)


class CandidateDecisionRequest(_BaseModel):
    reason: str = Field(default="", max_length=1024)


class CandidateResponse(_BaseModel):
    id: UUID
    tenant_id: UUID
    workspace_id: UUID | None
    kind: EvolveKind
    payload: dict[str, Any]
    confidence: float
    trigger_reason: str
    fingerprint: str
    status: EvolveStatus
    requester_id: UUID | None
    approver_id: UUID | None
    reviewed_at: datetime | None
    applied_at: datetime | None
    correlation_id: UUID | None
    expires_at: datetime
    created_at: datetime
    applied_summary: dict[str, Any] | None = None


class CandidateListResponse(_BaseModel):
    items: list[CandidateResponse]


class CandidateAppliedResponse(_BaseModel):
    candidate: CandidateResponse
    applied_summary: dict[str, Any]


__all__ = [
    "CandidateAppliedResponse",
    "CandidateDecisionRequest",
    "CandidateListResponse",
    "CandidateResponse",
    "CreateCandidateRequest",
]
