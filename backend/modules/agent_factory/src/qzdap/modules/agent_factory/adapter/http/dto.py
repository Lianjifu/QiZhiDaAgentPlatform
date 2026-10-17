"""HTTP DTOs for the agent_factory module."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateTemplateRequest(_StrictModel):
    name: str = Field(min_length=1, max_length=256)
    description: str = Field(default="", max_length=1024)
    # Phase 2: 接受 str (上游名) 或 UUID. router 端 resolve 成 UUID 再写库.
    default_model_id: str = Field(min_length=1, max_length=128)
    default_system_prompt: str = Field(min_length=1, max_length=32768)
    metadata: dict[str, Any] = Field(default_factory=dict)


class UpdateTemplateRequest(_StrictModel):
    status: str | None = None


class TemplateResponse(_StrictModel):
    id: str
    tenant_id: str
    workspace_id: str
    name: str
    description: str
    default_model_id: str | None
    default_system_prompt: str
    status: str
    metadata: dict[str, Any]
    created_by: str
    created_at: str
    updated_at: str


class TemplateListResponse(_StrictModel):
    items: list[TemplateResponse]
    count: int


class CreateVersionRequest(_StrictModel):
    version_tag: str = Field(min_length=1, max_length=64)
    system_prompt: str | None = Field(default=None, max_length=32768)
    # Phase 2: 接受 str (上游名) 或 UUID. router 端 resolve.
    model_id: str | None = Field(default=None, max_length=128)
    # Phase 15: 策略路由持久化. 至少其一可空.
    route_id: str | None = Field(default=None, max_length=36)
    route_strategy: str | None = Field(default=None, max_length=16)
    allowed_tools: list[str] = Field(default_factory=list)
    allowed_skills: list[str] = Field(default_factory=list)
    knowledge_package_ids: list[str] = Field(default_factory=list)
    plan_dsl_snapshot: dict[str, Any] | None = None
    max_total_steps: int | None = Field(default=None, ge=1, le=256)
    release_notes: str = Field(default="", max_length=4096)
    metadata: dict[str, Any] = Field(default_factory=dict)


class UpdateVersionNotesRequest(_StrictModel):
    release_notes: str = Field(min_length=1, max_length=4096)


class VersionResponse(_StrictModel):
    id: str
    tenant_id: str
    workspace_id: str
    template_id: str
    version_tag: str
    status: str
    system_prompt: str
    # Phase 2: 可能是 None (catalog 没建), 序列化为 str (UUID)
    model_id: str | None
    # Phase 15: 策略路由
    route_id: str | None
    route_strategy: str | None
    allowed_tools: list[str]
    allowed_skills: list[str]
    knowledge_package_ids: list[str]
    plan_dsl_snapshot: dict[str, Any] | None
    max_total_steps: int | None
    release_notes: str
    published_at: str | None
    released_at: str | None
    metadata: dict[str, Any]
    created_by: str
    created_at: str
    updated_at: str


class VersionListResponse(_StrictModel):
    items: list[VersionResponse]
    count: int


class ReleaseVersionRequest(_StrictModel):
    notes: str = Field(default="", max_length=4096)


class ReleaseResponse(_StrictModel):
    id: str
    tenant_id: str
    workspace_id: str
    template_id: str
    version_id: str
    eval_run_id: str | None
    eval_score: float | None
    status: str
    released_by: str
    released_at: str
    notes: str


class ReleaseListResponse(_StrictModel):
    items: list[ReleaseResponse]
    count: int


__all__ = [
    "CreateTemplateRequest",
    "CreateVersionRequest",
    "ReleaseListResponse",
    "ReleaseResponse",
    "ReleaseVersionRequest",
    "TemplateListResponse",
    "TemplateResponse",
    "UpdateTemplateRequest",
    "UpdateVersionNotesRequest",
    "VersionListResponse",
    "VersionResponse",
]
