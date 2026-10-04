"""Governance domain entities — PolicyRule / Approval / DecisionRecord.

All entities are frozen dataclasses with ``slots=True`` so they can be
hashed and safely passed across the async boundary. Mutations go through
factory / ``with_*`` methods that return new instances.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from qzdap_schema.ids import (
    ApprovalId,
    AuditLogId,
    DecisionEventId,
    PolicyId,
    TenantId,
    UserId,
    WorkspaceId,
)

from qzdap.modules.governance.domain.value_objects import (
    ApprovalStatus,
    PolicyEffect,
    PolicySubject,
)


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True, frozen=True)
class PolicyRule:
    """A single policy rule — JSON rule DSL persisted to ``policies``.

    Match semantics:
    - ``subject_type`` (``role`` / ``user`` / ``agent``) selects the
      kind of principal; ``subject_ref`` is the literal identifier
      (``workspace_member`` / UUID / ``agent:agt_x``).
    - ``action_pattern`` is a glob (``tool:execute:*`` matches
      ``tool:execute:reverse`` etc).
    - ``workspace_id`` is optional; ``None`` means the rule applies to
      all workspaces in the tenant.
    - Lower ``priority`` wins; ties broken by id.

    ``enabled=False`` excludes the rule from evaluation without deleting.
    """

    id: PolicyId
    tenant_id: TenantId
    workspace_id: WorkspaceId | None
    subject_type: PolicySubject
    subject_ref: str
    action_pattern: str
    effect: PolicyEffect
    priority: int = 100
    approval_required: bool = False
    quota: dict[str, Any] | None = None
    enabled: bool = True
    version_lock: int = 1
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)

    @classmethod
    def create(
        cls,
        *,
        tenant_id: TenantId,
        subject_type: PolicySubject,
        subject_ref: str,
        action_pattern: str,
        effect: PolicyEffect,
        workspace_id: WorkspaceId | None = None,
        priority: int = 100,
        approval_required: bool = False,
        quota: dict[str, Any] | None = None,
        enabled: bool = True,
        id: PolicyId | None = None,
        now: datetime | None = None,
    ) -> PolicyRule:
        from qzdap.modules.governance.domain.errors import InvalidPolicy

        if not subject_ref or not subject_ref.strip():
            raise InvalidPolicy("subject_ref must be non-empty")
        if not action_pattern or not action_pattern.strip():
            raise InvalidPolicy("action_pattern must be non-empty")
        if "*" in action_pattern and len(action_pattern) == 1:
            # bare ``*`` matches everything and is almost always a mistake
            raise InvalidPolicy("action_pattern '*' is too broad")
        ts = now or _utcnow()
        return cls(
            id=id if id is not None else PolicyId(uuid4()),  # type: ignore[arg-type]
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            subject_type=subject_type,
            subject_ref=subject_ref.strip(),
            action_pattern=action_pattern.strip(),
            effect=effect,
            priority=priority,
            approval_required=approval_required,
            quota=dict(quota) if quota else None,
            enabled=enabled,
            version_lock=1,
            created_at=ts,
            updated_at=ts,
        )


@dataclass(slots=True, frozen=True)
class Approval:
    """An approval request pending an operator decision."""

    id: ApprovalId
    tenant_id: TenantId
    requester_id: UserId
    action: str
    resource: dict[str, Any]
    payload: dict[str, Any]
    status: ApprovalStatus = ApprovalStatus.PENDING
    approver_id: UserId | None = None
    decided_at: datetime | None = None
    correlation_id: UUID | None = None
    expires_at: datetime = field(default_factory=_utcnow)
    created_at: datetime = field(default_factory=_utcnow)

    @classmethod
    def create(
        cls,
        *,
        tenant_id: TenantId,
        requester_id: UserId,
        action: str,
        resource: dict[str, Any],
        expires_at: datetime,
        payload: dict[str, Any] | None = None,
        correlation_id: UUID | None = None,
        id: ApprovalId | None = None,
        now: datetime | None = None,
    ) -> Approval:
        ts = now or _utcnow()
        return cls(
            id=id if id is not None else ApprovalId(uuid4()),  # type: ignore[arg-type]
            tenant_id=tenant_id,
            requester_id=requester_id,
            action=action,
            resource=dict(resource),
            payload=dict(payload or {}),
            status=ApprovalStatus.PENDING,
            expires_at=expires_at,
            correlation_id=correlation_id,
            created_at=ts,
        )

    def approve(self, *, approver_id: UserId, now: datetime | None = None) -> Approval:
        from qzdap.modules.governance.domain.errors import (
            ApprovalAlreadyDecided,
            ApproverMustDiffer,
        )

        if self.status is not ApprovalStatus.PENDING:
            raise ApprovalAlreadyDecided(
                f"approval {self.id} already {self.status.value}",
                code="APPROVAL_ALREADY_DECIDED",
            )
        if approver_id == self.requester_id:
            raise ApproverMustDiffer(
                "approver must differ from requester",
                code="APPROVER_MUST_DIFFER",
            )
        ts = now or _utcnow()
        return Approval(
            id=self.id,
            tenant_id=self.tenant_id,
            requester_id=self.requester_id,
            action=self.action,
            resource=dict(self.resource),
            payload=dict(self.payload),
            status=ApprovalStatus.APPROVED,
            approver_id=approver_id,
            decided_at=ts,
            correlation_id=self.correlation_id,
            expires_at=self.expires_at,
            created_at=self.created_at,
        )

    def deny(
        self,
        *,
        approver_id: UserId,
        reason: str = "",
        now: datetime | None = None,
    ) -> Approval:
        from qzdap.modules.governance.domain.errors import (
            ApprovalAlreadyDecided,
            ApproverMustDiffer,
        )

        if self.status is not ApprovalStatus.PENDING:
            raise ApprovalAlreadyDecided(
                f"approval {self.id} already {self.status.value}",
                code="APPROVAL_ALREADY_DECIDED",
            )
        if approver_id == self.requester_id:
            raise ApproverMustDiffer(
                "denier must differ from requester",
                code="APPROVER_MUST_DIFFER",
            )
        ts = now or _utcnow()
        new_payload = dict(self.payload)
        if reason:
            new_payload["deny_reason"] = reason
        return Approval(
            id=self.id,
            tenant_id=self.tenant_id,
            requester_id=self.requester_id,
            action=self.action,
            resource=dict(self.resource),
            payload=new_payload,
            status=ApprovalStatus.DENIED,
            approver_id=approver_id,
            decided_at=ts,
            correlation_id=self.correlation_id,
            expires_at=self.expires_at,
            created_at=self.created_at,
        )

    def expire(self, *, now: datetime | None = None) -> Approval:
        from qzdap.modules.governance.domain.errors import ApprovalAlreadyDecided

        if self.status is not ApprovalStatus.PENDING:
            raise ApprovalAlreadyDecided(
                f"approval {self.id} already {self.status.value}",
                code="APPROVAL_ALREADY_DECIDED",
            )
        ts = now or _utcnow()
        return Approval(
            id=self.id,
            tenant_id=self.tenant_id,
            requester_id=self.requester_id,
            action=self.action,
            resource=dict(self.resource),
            payload=dict(self.payload),
            status=ApprovalStatus.EXPIRED,
            approver_id=self.approver_id,
            decided_at=ts,
            correlation_id=self.correlation_id,
            expires_at=self.expires_at,
            created_at=self.created_at,
        )


@dataclass(slots=True, frozen=True)
class DecisionRecord:
    """The outcome of evaluating a single policy decision.

    Returned by ``PolicyEvaluator.evaluate()`` and consumed by the
    ``PolicyGuard`` to decide whether to raise ``ActionDeniedError``
    or ``ApprovalRequiredError``, or to let the call through.
    """

    effect: PolicyEffect
    rule_id: PolicyId | None
    reason: str
    approval_id: ApprovalId | None = None
    latency_ms: int = 0


@dataclass(slots=True, frozen=True)
class AuditLogEntry:
    id: AuditLogId
    tenant_id: TenantId
    actor_id: UserId | None
    event_type: str
    payload: dict[str, Any]
    created_at: datetime = field(default_factory=_utcnow)


@dataclass(slots=True, frozen=True)
class DecisionEvent:
    """Append-only record of one policy decision."""

    id: DecisionEventId
    tenant_id: TenantId
    actor_id: UserId
    action: str
    effect: PolicyEffect
    resource: dict[str, Any] | None
    rule_id: PolicyId | None
    approval_id: ApprovalId | None
    latency_ms: int
    created_at: datetime = field(default_factory=_utcnow)


__all__ = [
    "Approval",
    "AuditLogEntry",
    "DecisionEvent",
    "DecisionRecord",
    "PolicyRule",
]
