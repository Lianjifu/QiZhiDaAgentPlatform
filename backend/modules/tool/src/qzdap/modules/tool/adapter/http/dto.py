"""HTTP-layer DTOs for the tool module."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class AuthConfigDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["none", "bearer", "api_key", "oauth2"] = "none"
    secrets_ref: str | None = None


class SpecOperationDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    method: Literal["GET", "POST", "PUT", "DELETE", "PATCH"]
    path: str
    operation_id: str


class ToolResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    tenant_id: str
    workspace_id: str
    name: str
    description: str
    protocol: Literal["custom", "openapi", "mcp"]
    spec: dict[str, Any]
    spec_operations: list[SpecOperationDTO]
    auth_config: AuthConfigDTO | None
    rate_limit_per_minute: int | None
    enabled: bool
    version: int
    created_at: str
    updated_at: str


class ToolListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ToolResponse]
    total: int


class RegisterToolRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=128)
    description: str = ""
    protocol: Literal["custom", "openapi", "mcp"]
    spec: dict[str, Any] = Field(default_factory=dict)
    auth_config: AuthConfigDTO | None = None
    rate_limit_per_minute: int | None = Field(default=None, ge=1, le=100_000)


class UpdateToolRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str | None = None
    spec: dict[str, Any] | None = None
    auth_config: AuthConfigDTO | None = None
    clear_auth: bool = False
    rate_limit_per_minute: int | None = None
    clear_rate_limit: bool = False
    enabled: bool | None = None


class InvokeToolRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolCallResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_name: str
    status: int
    result: dict[str, Any] | None
    latency_ms: int | None
    error: dict[str, Any] | None = None


class BatchInvokeInputDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class BatchInvokeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    calls: list[BatchInvokeInputDTO] = Field(min_length=1, max_length=50)


class BatchInvokeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ToolCallResponse]
