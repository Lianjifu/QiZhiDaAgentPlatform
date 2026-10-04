"""Governance domain events — published to EventBus on lifecycle transitions.

Topics follow the convention ``governance.<aggregate>.<verb>`` so the
``audit_subscriber`` can subscribe with a wildcard (``governance.*``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from qzdap_kernel.events import DomainEvent
from qzdap_schema.ids import (
    ApprovalId,
    AuditLogId,
    PolicyId,
    TenantId,
    UserId,
)

from qzdap.modules.governance.domain.value_objects import (
    ApprovalStatus,
    PolicyEffect,
)


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True, frozen=True)
class PolicyCreated(DomainEvent):
    tenant_id: TenantId
    actor_id: UserId
    rule_id: PolicyId
    effect: PolicyEffect
    action_pattern: str
    occurred_at: datetime = field(default_factory=_utcnow)
    event_id: UUID = field(default_factory=uuid4)
    correlation_id: UUID | None = None

    @property
    def topic(self) -> str:
        return "governance.policy.created"


@dataclass(slots=True, frozen=True)
class PolicyUpdated(DomainEvent):
    tenant_id: TenantId
    actor_id: UserId
    rule_id: PolicyId
    enabled: bool
    occurred_at: datetime = field(default_factory=_utcnow)
    event_id: UUID = field(default_factory=uuid4)
    correlation_id: UUID | None = None

    @property
    def topic(self) -> str:
        return "governance.policy.updated"


@dataclass(slots=True, frozen=True)
class PolicyDeleted(DomainEvent):
    tenant_id: TenantId
    actor_id: UserId
    rule_id: PolicyId
    occurred_at: datetime = field(default_factory=_utcnow)
    event_id: UUID = field(default_factory=uuid4)
    correlation_id: UUID | None = None

    @property
    def topic(self) -> str:
        return "governance.policy.deleted"


@dataclass(slots=True, frozen=True)
class ApprovalRequested(DomainEvent):
    tenant_id: TenantId
    requester_id: UserId
    approval_id: ApprovalId
    action: str
    resource: dict[str, Any]
    occurred_at: datetime = field(default_factory=_utcnow)
    event_id: UUID = field(default_factory=uuid4)
    correlation_id: UUID | None = None

    @property
    def topic(self) -> str:
        return "governance.approval.requested"


@dataclass(slots=True, frozen=True)
class ApprovalDecided(DomainEvent):
    tenant_id: TenantId
    approver_id: UserId
    approval_id: ApprovalId
    status: ApprovalStatus
    occurred_at: datetime = field(default_factory=_utcnow)
    event_id: UUID = field(default_factory=uuid4)
    correlation_id: UUID | None = None

    @property
    def topic(self) -> str:
        return "governance.approval.decided"


@dataclass(slots=True, frozen=True)
class DecisionRecorded(DomainEvent):
    tenant_id: TenantId
    actor_id: UserId
    action: str
    effect: PolicyEffect
    rule_id: PolicyId | None
    approval_id: ApprovalId | None
    latency_ms: int
    occurred_at: datetime = field(default_factory=_utcnow)
    event_id: UUID = field(default_factory=uuid4)
    correlation_id: UUID | None = None

    @property
    def topic(self) -> str:
        return "governance.decision.recorded"


@dataclass(slots=True, frozen=True)
class AuditLogAppended(DomainEvent):
    tenant_id: TenantId
    actor_id: UserId | None
    event_type: str
    payload: dict[str, Any]
    audit_id: AuditLogId
    occurred_at: datetime = field(default_factory=_utcnow)
    event_id: UUID = field(default_factory=uuid4)
    correlation_id: UUID | None = None

    @property
    def topic(self) -> str:
        return "governance.audit.appended"


__all__ = [
    "ApprovalDecided",
    "ApprovalRequested",
    "AuditLogAppended",
    "DecisionRecorded",
    "PolicyCreated",
    "PolicyDeleted",
    "PolicyUpdated",
]
