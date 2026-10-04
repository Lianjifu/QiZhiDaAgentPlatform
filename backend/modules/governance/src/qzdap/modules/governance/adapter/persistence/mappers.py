"""Governance ORM ↔ domain mappers.

ORM → domain returns frozen dataclasses.  Domain → ORM materialises a
new ORM row (caller is responsible for ``add()``/``update()``).

These are pure functions so they are easy to unit-test.
"""

from __future__ import annotations

from uuid import UUID

from qzdap_schema.ids import (
    ApprovalId,
    AuditLogId,
    DecisionEventId,
    PolicyId,
    TenantId,
    UserId,
    WorkspaceId,
)

from qzdap.modules.governance.adapter.persistence.models import (
    ApprovalORM,
    AuditLogORM,
    DecisionEventORM,
    PolicyORM,
)
from qzdap.modules.governance.domain.entities import (
    Approval,
    AuditLogEntry,
    DecisionEvent,
    PolicyRule,
)
from qzdap.modules.governance.domain.value_objects import (
    ApprovalStatus,
    PolicyEffect,
    PolicySubject,
)


def policy_to_domain(row: PolicyORM) -> PolicyRule:
    return PolicyRule(
        id=PolicyId(row.id),
        tenant_id=TenantId(row.tenant_id),
        workspace_id=WorkspaceId(row.workspace_id) if row.workspace_id else None,
        subject_type=PolicySubject(row.subject_type),
        subject_ref=row.subject_ref,
        action_pattern=row.action_pattern,
        effect=PolicyEffect(row.effect),
        priority=row.priority,
        approval_required=row.approval_required,
        quota=dict(row.quota) if row.quota else None,
        enabled=row.enabled,
        version_lock=row.version_lock,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def policy_to_orm(rule: PolicyRule) -> PolicyORM:
    return PolicyORM(
        id=UUID(str(rule.id)),
        tenant_id=UUID(str(rule.tenant_id)),
        workspace_id=UUID(str(rule.workspace_id)) if rule.workspace_id else None,
        subject_type=rule.subject_type.value,
        subject_ref=rule.subject_ref,
        action_pattern=rule.action_pattern,
        effect=rule.effect.value,
        priority=rule.priority,
        approval_required=rule.approval_required,
        quota=dict(rule.quota) if rule.quota else None,
        enabled=rule.enabled,
        version_lock=rule.version_lock,
        created_at=rule.created_at,
        updated_at=rule.updated_at,
    )


def approval_to_domain(row: ApprovalORM) -> Approval:
    return Approval(
        id=ApprovalId(row.id),
        tenant_id=TenantId(row.tenant_id),
        requester_id=UserId(row.requester_id),
        action=row.action,
        resource=dict(row.resource or {}),
        payload=dict(row.payload or {}),
        status=ApprovalStatus(row.status),
        approver_id=UserId(row.approver_id) if row.approver_id else None,
        decided_at=row.decided_at,
        correlation_id=row.correlation_id,
        expires_at=row.expires_at,
        created_at=row.created_at,
    )


def approval_to_orm(approval: Approval) -> ApprovalORM:
    return ApprovalORM(
        id=UUID(str(approval.id)),
        tenant_id=UUID(str(approval.tenant_id)),
        requester_id=UUID(str(approval.requester_id)),
        action=approval.action,
        resource=dict(approval.resource),
        payload=dict(approval.payload),
        status=approval.status.value,
        approver_id=UUID(str(approval.approver_id)) if approval.approver_id else None,
        decided_at=approval.decided_at,
        correlation_id=approval.correlation_id,
        expires_at=approval.expires_at,
        created_at=approval.created_at,
    )


def decision_event_to_domain(row: DecisionEventORM) -> DecisionEvent:
    return DecisionEvent(
        id=DecisionEventId(row.id),
        tenant_id=TenantId(row.tenant_id),
        actor_id=UserId(row.actor_id),
        action=row.action,
        effect=PolicyEffect(row.effect),
        resource=dict(row.resource) if row.resource else None,
        rule_id=PolicyId(row.rule_id) if row.rule_id else None,
        approval_id=ApprovalId(row.approval_id) if row.approval_id else None,
        latency_ms=row.latency_ms,
        created_at=row.created_at,
    )


def decision_event_to_orm(event: DecisionEvent) -> DecisionEventORM:
    return DecisionEventORM(
        id=UUID(str(event.id)),
        tenant_id=UUID(str(event.tenant_id)),
        actor_id=UUID(str(event.actor_id)),
        action=event.action,
        effect=event.effect.value,
        resource=dict(event.resource) if event.resource else None,
        rule_id=UUID(str(event.rule_id)) if event.rule_id else None,
        approval_id=UUID(str(event.approval_id)) if event.approval_id else None,
        latency_ms=event.latency_ms,
        created_at=event.created_at,
    )


def audit_to_domain(row: AuditLogORM) -> AuditLogEntry:
    return AuditLogEntry(
        id=AuditLogId(row.id),
        tenant_id=TenantId(row.tenant_id),
        actor_id=UserId(row.actor_id) if row.actor_id else None,
        event_type=row.event_type,
        payload=dict(row.payload or {}),
        created_at=row.created_at,
    )


def audit_to_orm(entry: AuditLogEntry) -> AuditLogORM:
    return AuditLogORM(
        id=UUID(str(entry.id)),
        tenant_id=UUID(str(entry.tenant_id)),
        actor_id=UUID(str(entry.actor_id)) if entry.actor_id else None,
        event_type=entry.event_type,
        payload=dict(entry.payload),
        created_at=entry.created_at,
    )


__all__ = [
    "approval_to_domain",
    "approval_to_orm",
    "audit_to_domain",
    "audit_to_orm",
    "decision_event_to_domain",
    "decision_event_to_orm",
    "policy_to_domain",
    "policy_to_orm",
]
