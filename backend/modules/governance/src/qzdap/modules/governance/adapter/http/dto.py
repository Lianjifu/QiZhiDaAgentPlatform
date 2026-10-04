"""Governance HTTP DTOs — request / response shapes for /v1/policies/* and /v1/approvals/*."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from qzdap.modules.governance.domain.value_objects import (
    ApprovalStatus,
    PolicyEffect,
    PolicySubject,
)


class _BaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class CreatePolicyRequest(_BaseModel):
    subject_type: PolicySubject
    subject_ref: str = Field(min_length=1, max_length=256)
    action_pattern: str = Field(min_length=1, max_length=256)
    effect: PolicyEffect
    workspace_id: UUID | None = None
    priority: int = 100
    approval_required: bool = False
    quota: dict[str, Any] | None = None
    enabled: bool = True


class UpdatePolicyRequest(_BaseModel):
    enabled: bool | None = None
    priority: int | None = None
    effect: PolicyEffect | None = None
    action_pattern: str | None = None


class PolicyResponse(_BaseModel):
    id: UUID
    tenant_id: UUID
    workspace_id: UUID | None
    subject_type: PolicySubject
    subject_ref: str
    action_pattern: str
    effect: PolicyEffect
    priority: int
    approval_required: bool
    quota: dict[str, Any] | None
    enabled: bool
    version_lock: int
    created_at: datetime
    updated_at: datetime


class PolicyListResponse(_BaseModel):
    items: list[PolicyResponse]
    next_cursor: str | None = None


class ApprovalResponse(_BaseModel):
    id: UUID
    tenant_id: UUID
    requester_id: UUID
    action: str
    resource: dict[str, Any]
    payload: dict[str, Any]
    status: ApprovalStatus
    approver_id: UUID | None
    decided_at: datetime | None
    correlation_id: UUID | None
    expires_at: datetime
    created_at: datetime


class ApprovalListResponse(_BaseModel):
    items: list[ApprovalResponse]


class ApprovalDecisionRequest(_BaseModel):
    reason: str = Field(default="", max_length=1024)


__all__ = [
    "ApprovalDecisionRequest",
    "ApprovalListResponse",
    "ApprovalResponse",
    "CreatePolicyRequest",
    "PolicyListResponse",
    "PolicyResponse",
    "UpdatePolicyRequest",
]
