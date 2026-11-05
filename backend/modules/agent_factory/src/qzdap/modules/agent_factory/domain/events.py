"""Agent factory domain events emitted through the messaging bus."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from qzdap_kernel.events import DomainEvent
from qzdap_kernel.ids import (
    AgentTemplateId,
    AgentVersionId,
    EvalRunId,
    ReleaseId,
    TenantId,
    UserId,
    WorkspaceId,
)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _event_id() -> UUID:
    return uuid4()


@dataclass(slots=True, frozen=True)
class AgentTemplateCreated(DomainEvent):
    TOPIC = "agent_factory.template.created"

    template_id: AgentTemplateId
    tenant_id: TenantId
    workspace_id: WorkspaceId
    name: str
    created_by: UserId
    event_id: UUID = field(default_factory=_event_id)
    occurred_at: datetime = field(default_factory=_utcnow)
    event_name: str = "agent_factory.template.created"

    def to_payload(self) -> dict[str, Any]:
        return {
            "template_id": str(self.template_id),
            "tenant_id": str(self.tenant_id),
            "workspace_id": str(self.workspace_id),
            "name": self.name,
            "created_by": str(self.created_by),
        }


@dataclass(slots=True, frozen=True)
class AgentVersionPublished(DomainEvent):
    TOPIC = "agent_factory.version.published"

    template_id: AgentTemplateId
    version_id: AgentVersionId
    tenant_id: TenantId
    workspace_id: WorkspaceId
    version_tag: str
    event_id: UUID = field(default_factory=_event_id)
    occurred_at: datetime = field(default_factory=_utcnow)
    event_name: str = "agent_factory.version.published"

    def to_payload(self) -> dict[str, Any]:
        return {
            "template_id": str(self.template_id),
            "version_id": str(self.version_id),
            "tenant_id": str(self.tenant_id),
            "workspace_id": str(self.workspace_id),
            "version_tag": self.version_tag,
        }


@dataclass(slots=True, frozen=True)
class AgentReleased(DomainEvent):
    TOPIC = "agent_factory.version.released"

    release_id: ReleaseId
    template_id: AgentTemplateId
    version_id: AgentVersionId
    tenant_id: TenantId
    workspace_id: WorkspaceId
    eval_run_id: EvalRunId | None
    eval_score: float | None
    released_by: UserId
    #: **版本绑的策略路由** ✓（UUID ✓）—— 随发布事件带走 ✓，这样 runtime
    #: 那侧的 catalog agent **能拿到路由** ✓（之前这一路是断的 ✗✗ —— 版本存了
    #: 路由，但对话路径永远读不到 ✓）。
    route_id: UUID | None = None
    #: **版本指定的路由策略** ✓（覆盖 route 自带的 strategy ✓）。
    route_strategy: str | None = None
    event_id: UUID = field(default_factory=_event_id)
    occurred_at: datetime = field(default_factory=_utcnow)
    event_name: str = "agent_factory.version.released"

    def to_payload(self) -> dict[str, Any]:
        return {
            "release_id": str(self.release_id),
            "template_id": str(self.template_id),
            "version_id": str(self.version_id),
            "tenant_id": str(self.tenant_id),
            "workspace_id": str(self.workspace_id),
            "eval_run_id": str(self.eval_run_id) if self.eval_run_id else None,
            "eval_score": self.eval_score,
            "released_by": str(self.released_by),
            "route_id": str(self.route_id) if self.route_id else None,
            "route_strategy": self.route_strategy,
        }


__all__ = [
    "AgentReleased",
    "AgentTemplateCreated",
    "AgentVersionPublished",
]
