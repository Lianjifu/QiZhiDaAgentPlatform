"""ORM ↔ domain mappers for self-evolution.

Pure functions, easy to unit-test. Domain → ORM returns a fresh ORM row;
the caller is responsible for ``add()`` / ``update()``.
"""

from __future__ import annotations

from uuid import UUID

from qzdap_schema.ids import (
    EvolveCandidateId,
    TenantId,
    UserId,
    WorkspaceId,
)

from qzdap.modules.self_evolution.adapter.persistence.models import (
    EvolveCandidateORM,
)
from qzdap.modules.self_evolution.domain.entities import EvolveCandidate
from qzdap.modules.self_evolution.domain.value_objects import (
    EvolveKind,
    EvolveStatus,
)


def candidate_to_domain(row: EvolveCandidateORM) -> EvolveCandidate:
    return EvolveCandidate(
        id=EvolveCandidateId(row.id),
        tenant_id=TenantId(row.tenant_id),
        workspace_id=WorkspaceId(row.workspace_id) if row.workspace_id else None,
        kind=EvolveKind(row.kind),
        payload=dict(row.payload or {}),
        confidence=float(row.confidence),
        trigger_reason=row.trigger_reason,
        fingerprint=row.fingerprint,
        status=EvolveStatus(row.status),
        requester_id=UserId(row.requester_id) if row.requester_id else None,
        approver_id=UserId(row.approver_id) if row.approver_id else None,
        reviewed_at=row.reviewed_at,
        applied_at=row.applied_at,
        correlation_id=row.correlation_id,
        expires_at=row.expires_at,
        created_at=row.created_at,
    )


def candidate_to_orm(cand: EvolveCandidate) -> EvolveCandidateORM:
    return EvolveCandidateORM(
        id=UUID(str(cand.id)),
        tenant_id=UUID(str(cand.tenant_id)),
        workspace_id=UUID(str(cand.workspace_id)) if cand.workspace_id else None,
        kind=cand.kind.value,
        payload=dict(cand.payload),
        confidence=cand.confidence,
        trigger_reason=cand.trigger_reason,
        fingerprint=cand.fingerprint,
        status=cand.status.value,
        requester_id=UUID(str(cand.requester_id)) if cand.requester_id else None,
        approver_id=UUID(str(cand.approver_id)) if cand.approver_id else None,
        reviewed_at=cand.reviewed_at,
        applied_at=cand.applied_at,
        correlation_id=cand.correlation_id,
        expires_at=cand.expires_at,
        created_at=cand.created_at,
        updated_at=cand.created_at,
    )


__all__ = ["candidate_to_domain", "candidate_to_orm"]
