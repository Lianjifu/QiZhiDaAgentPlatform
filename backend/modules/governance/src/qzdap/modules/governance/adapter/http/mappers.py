"""Domain <-> DTO converters for the HTTP layer."""

from __future__ import annotations

from typing import Any

from qzdap.modules.governance.adapter.http.dto import (
    ApprovalResponse,
    PolicyResponse,
)
from qzdap.modules.governance.domain.entities import Approval, PolicyRule


def policy_to_response(rule: PolicyRule) -> PolicyResponse:
    return PolicyResponse(
        id=rule.id,  # type: ignore[arg-type]
        tenant_id=rule.tenant_id,  # type: ignore[arg-type]
        workspace_id=rule.workspace_id,  # type: ignore[arg-type]
        subject_type=rule.subject_type,
        subject_ref=rule.subject_ref,
        action_pattern=rule.action_pattern,
        effect=rule.effect,
        priority=rule.priority,
        approval_required=rule.approval_required,
        quota=dict(rule.quota) if rule.quota else None,
        enabled=rule.enabled,
        version_lock=rule.version_lock,
        created_at=rule.created_at,
        updated_at=rule.updated_at,
    )


def approval_to_response(approval: Approval) -> ApprovalResponse:
    return ApprovalResponse(
        id=approval.id,  # type: ignore[arg-type]
        tenant_id=approval.tenant_id,  # type: ignore[arg-type]
        requester_id=approval.requester_id,  # type: ignore[arg-type]
        action=approval.action,
        resource=dict(approval.resource),
        payload=dict(approval.payload),
        status=approval.status,
        approver_id=approval.approver_id,  # type: ignore[arg-type]
        decided_at=approval.decided_at,
        correlation_id=approval.correlation_id,
        expires_at=approval.expires_at,
        created_at=approval.created_at,
    )


__all__ = ["approval_to_response", "policy_to_response"]


# forward reference helper for callers that need a dict body
def response_as_dict(model: Any) -> dict[str, Any]:
    return model.model_dump(mode="json")
