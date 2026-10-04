"""HTTP DTOs for the platform module."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PlanResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    code: str
    display_name: str
    description: str
    limits: dict[str, Any]
    features: tuple[str, ...]
    price_monthly_usd: str = Field(..., description="Decimal serialized as str")
    status: str
    sort_order: int
    created_at: datetime
    updated_at: datetime


class PlanListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[PlanResponse]
    count: int


class SubscriptionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    tenant_id: UUID
    plan_id: UUID
    plan_code: str
    status: str
    started_at: datetime
    ends_at: datetime | None
    auto_renew: bool
    updated_by: UUID | None
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class AssignSubscriptionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_code: str
    auto_renew: bool = True


class TenantSettingResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    tenant_id: UUID
    workspace_id: UUID | None
    key: str
    value: Any
    updated_by: UUID | None
    created_at: datetime
    updated_at: datetime


class TenantSettingListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[TenantSettingResponse]
    count: int


class UpsertSettingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: Any
    workspace_id: UUID | None = None


__all__ = [
    "AssignSubscriptionRequest",
    "PlanListResponse",
    "PlanResponse",
    "SubscriptionResponse",
    "TenantSettingListResponse",
    "TenantSettingResponse",
    "UpsertSettingRequest",
]
