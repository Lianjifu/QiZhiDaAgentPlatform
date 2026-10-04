"""HTTP DTOs for the agent runtime."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class CreateSessionRequest(BaseModel):
    agent_version: str = Field(min_length=1, max_length=64)
    metadata: dict = Field(default_factory=dict)


class SessionResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    workspace_id: UUID
    owner_id: UUID
    agent_id: UUID
    agent_version: str
    status: Literal["open", "closed"]
    created_at: datetime
    closed_at: datetime | None = None
    metadata: dict


class RunTurnRequest(BaseModel):
    content: str = Field(min_length=1, max_length=64_000)
    model: str | None = Field(default=None, max_length=128)
    metadata: dict = Field(default_factory=dict)


class TurnResponse(BaseModel):
    id: UUID
    session_id: UUID
    status: Literal["running", "succeeded", "failed", "denied"]
    started_at: datetime
    finished_at: datetime | None = None
    final_response: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    error_code: str | None = None
