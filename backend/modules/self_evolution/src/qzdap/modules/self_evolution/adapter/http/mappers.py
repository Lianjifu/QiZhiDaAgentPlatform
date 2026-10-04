"""Domain ↔ HTTP DTO mappers."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from qzdap.modules.self_evolution.adapter.http.dto import CandidateResponse
from qzdap.modules.self_evolution.domain.entities import EvolveCandidate


def candidate_to_response(
    cand: EvolveCandidate, *, applied_summary: dict[str, Any] | None = None
) -> CandidateResponse:
    return CandidateResponse(
        id=UUID(str(cand.id)),
        tenant_id=UUID(str(cand.tenant_id)),
        workspace_id=UUID(str(cand.workspace_id)) if cand.workspace_id else None,
        kind=cand.kind,
        payload=dict(cand.payload),
        confidence=cand.confidence,
        trigger_reason=cand.trigger_reason,
        fingerprint=cand.fingerprint,
        status=cand.status,
        requester_id=UUID(str(cand.requester_id)) if cand.requester_id else None,
        approver_id=UUID(str(cand.approver_id)) if cand.approver_id else None,
        reviewed_at=cand.reviewed_at,
        applied_at=cand.applied_at,
        correlation_id=cand.correlation_id,
        expires_at=cand.expires_at,
        created_at=cand.created_at,
        applied_summary=applied_summary,
    )


__all__ = ["candidate_to_response"]
