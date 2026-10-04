"""Self-evolution domain entities — EvolveCandidate.

Single frozen dataclass; transitions go through ``approve / reject /
mark_applied`` methods that raise ``EvolveCandidateAlreadyDecided`` /
``SignerMustDiffer`` on illegal moves. The ``fingerprint`` is computed
from the canonical payload so the UQ constraint on (tenant_id,
fingerprint) dedupes identical candidates.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Self
from uuid import UUID, uuid4

from qzdap_schema.ids import (
    EvolveCandidateId,
    TenantId,
    UserId,
    WorkspaceId,
)

from qzdap.modules.self_evolution.domain.errors import (
    EvolveCandidateAlreadyDecided,
    InvalidEvolveCandidate,
    SignerMustDiffer,
)
from qzdap.modules.self_evolution.domain.value_objects import (
    EvolveKind,
    EvolveStatus,
)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def compute_fingerprint(
    *,
    tenant_id: TenantId,
    kind: EvolveKind,
    payload: dict[str, Any],
) -> str:
    """sha256 over (tenant_id || kind || canonical_payload) — 64 hex chars."""
    blob = {
        "tenant_id": str(tenant_id),
        "kind": kind.value,
        "payload": dict(payload),
    }
    encoded = json.dumps(blob, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(slots=True, frozen=True)
class EvolveCandidate:
    id: EvolveCandidateId
    tenant_id: TenantId
    workspace_id: WorkspaceId | None
    kind: EvolveKind
    payload: dict[str, Any]
    confidence: float
    trigger_reason: str
    fingerprint: str
    status: EvolveStatus = EvolveStatus.PENDING
    requester_id: UserId | None = None
    approver_id: UserId | None = None
    reviewed_at: datetime | None = None
    applied_at: datetime | None = None
    correlation_id: UUID | None = None
    expires_at: datetime = field(default_factory=_utcnow)
    created_at: datetime = field(default_factory=_utcnow)

    @classmethod
    def create(
        cls,
        *,
        tenant_id: TenantId,
        kind: EvolveKind,
        payload: dict[str, Any],
        confidence: float,
        trigger_reason: str,
        workspace_id: WorkspaceId | None = None,
        requester_id: UserId | None = None,
        ttl_seconds: int = 3600,
        correlation_id: UUID | None = None,
        fingerprint: str | None = None,
        now: datetime | None = None,
    ) -> Self:
        if not 0.0 <= confidence <= 1.0:
            raise InvalidEvolveCandidate(
                f"confidence {confidence} not in [0.0, 1.0]",
                code="INVALID_EVOLVE_CANDIDATE",
            )
        if not trigger_reason or not trigger_reason.strip():
            raise InvalidEvolveCandidate(
                "trigger_reason must be non-empty",
                code="INVALID_EVOLVE_CANDIDATE",
            )
        if len(trigger_reason) > 256:
            raise InvalidEvolveCandidate(
                f"trigger_reason length {len(trigger_reason)} > 256",
                code="INVALID_EVOLVE_CANDIDATE",
            )
        if ttl_seconds <= 0:
            raise InvalidEvolveCandidate(
                f"ttl_seconds {ttl_seconds} must be > 0",
                code="INVALID_EVOLVE_CANDIDATE",
            )
        ts = now or _utcnow()
        fp = (
            fingerprint
            if fingerprint is not None
            else compute_fingerprint(tenant_id=tenant_id, kind=kind, payload=payload)
        )
        return cls(
            id=EvolveCandidateId(uuid4()),  # type: ignore[arg-type]
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            kind=kind,
            payload=dict(payload),
            confidence=float(confidence),
            trigger_reason=trigger_reason.strip(),
            fingerprint=fp,
            status=EvolveStatus.PENDING,
            requester_id=requester_id,
            approver_id=None,
            reviewed_at=None,
            applied_at=None,
            correlation_id=correlation_id,
            expires_at=ts + timedelta(seconds=ttl_seconds),
            created_at=ts,
        )

    def approve(
        self,
        *,
        approver_id: UserId,
        now: datetime | None = None,
    ) -> Self:
        if self.status is not EvolveStatus.PENDING:
            raise EvolveCandidateAlreadyDecided(
                f"candidate {self.id} already {self.status.value}",
                code="EVOLVE_CANDIDATE_ALREADY_DECIDED",
            )
        if self.requester_id is not None and approver_id == self.requester_id:
            raise SignerMustDiffer(
                "approver must differ from requester",
                code="EVOLVE_SIGNER_MUST_DIFFER",
            )
        ts = now or _utcnow()
        return type(self)(
            id=self.id,
            tenant_id=self.tenant_id,
            workspace_id=self.workspace_id,
            kind=self.kind,
            payload=dict(self.payload),
            confidence=self.confidence,
            trigger_reason=self.trigger_reason,
            fingerprint=self.fingerprint,
            status=EvolveStatus.APPROVED,
            requester_id=self.requester_id,
            approver_id=approver_id,
            reviewed_at=ts,
            applied_at=self.applied_at,
            correlation_id=self.correlation_id,
            expires_at=self.expires_at,
            created_at=self.created_at,
        )

    def reject(
        self,
        *,
        approver_id: UserId,
        now: datetime | None = None,
    ) -> Self:
        if self.status is not EvolveStatus.PENDING:
            raise EvolveCandidateAlreadyDecided(
                f"candidate {self.id} already {self.status.value}",
                code="EVOLVE_CANDIDATE_ALREADY_DECIDED",
            )
        if self.requester_id is not None and approver_id == self.requester_id:
            raise SignerMustDiffer(
                "denier must differ from requester",
                code="EVOLVE_SIGNER_MUST_DIFFER",
            )
        ts = now or _utcnow()
        return type(self)(
            id=self.id,
            tenant_id=self.tenant_id,
            workspace_id=self.workspace_id,
            kind=self.kind,
            payload=dict(self.payload),
            confidence=self.confidence,
            trigger_reason=self.trigger_reason,
            fingerprint=self.fingerprint,
            status=EvolveStatus.REJECTED,
            requester_id=self.requester_id,
            approver_id=approver_id,
            reviewed_at=ts,
            applied_at=self.applied_at,
            correlation_id=self.correlation_id,
            expires_at=self.expires_at,
            created_at=self.created_at,
        )

    def mark_applied(self, *, now: datetime | None = None) -> Self:
        if self.status is not EvolveStatus.APPROVED:
            raise EvolveCandidateAlreadyDecided(
                f"candidate {self.id} must be APPROVED before apply, got {self.status.value}",
                code="EVOLVE_CANDIDATE_ALREADY_DECIDED",
            )
        ts = now or _utcnow()
        return type(self)(
            id=self.id,
            tenant_id=self.tenant_id,
            workspace_id=self.workspace_id,
            kind=self.kind,
            payload=dict(self.payload),
            confidence=self.confidence,
            trigger_reason=self.trigger_reason,
            fingerprint=self.fingerprint,
            status=EvolveStatus.APPLIED,
            requester_id=self.requester_id,
            approver_id=self.approver_id,
            reviewed_at=self.reviewed_at,
            applied_at=ts,
            correlation_id=self.correlation_id,
            expires_at=self.expires_at,
            created_at=self.created_at,
        )


__all__ = ["EvolveCandidate", "compute_fingerprint"]
