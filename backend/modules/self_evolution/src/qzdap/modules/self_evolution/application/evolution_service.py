"""EvolutionCandidateService — create / approve / reject / apply.

Mirrors ``ApprovalService`` from P5 governance: pure service object that
calls the repo + publishes events. TTL is in seconds (default 1h).
Expiration transitions a still-pending candidate into ``rejected`` so the
status stays monotonic. ``apply()`` is the only state-changing call that
delegates to an :class:`ApplyGuard`.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from qzdap_schema.ids import (
    EvolveCandidateId,
    TenantId,
    UserId,
    WorkspaceId,
)

from qzdap.modules.self_evolution.application.apply_guard import (
    ApplyGuard,
    ApplyOutcome,
)
from qzdap.modules.self_evolution.application.ports import (
    ClockPort,
    EvolutionCandidateRepository,
    EvolutionEventPublisher,
    IdGeneratorPort,
)
from qzdap.modules.self_evolution.domain.entities import EvolveCandidate
from qzdap.modules.self_evolution.domain.errors import (
    EvolveCandidateAlreadyDecided,
    EvolveCandidateNotFound,
)
from qzdap.modules.self_evolution.domain.events import (
    EvolutionCandidateApplied,
    EvolutionCandidateCreated,
    EvolutionCandidateDecided,
)
from qzdap.modules.self_evolution.domain.value_objects import (
    EvolveKind,
    EvolveStatus,
    is_terminal,
)


class EvolutionCandidateService:
    def __init__(
        self,
        *,
        repo: EvolutionCandidateRepository,
        clock: ClockPort,
        ids: IdGeneratorPort,
        apply_guard: ApplyGuard,
        publisher: EvolutionEventPublisher | None = None,
        default_ttl_seconds: int = 3600,
    ) -> None:
        self._repo = repo
        self._clock = clock
        self._ids = ids
        self._guard = apply_guard
        self._publisher = publisher
        self._default_ttl = default_ttl_seconds

    # ── create ─────────────────────────────────────────────────────────

    async def create(
        self,
        *,
        tenant_id: TenantId,
        kind: EvolveKind,
        payload: dict[str, Any],
        confidence: float,
        trigger_reason: str,
        workspace_id: WorkspaceId | None = None,
        requester_id: UserId | None = None,
        ttl_seconds: int | None = None,
        correlation_id: UUID | None = None,
    ) -> EvolveCandidate:
        candidate = EvolveCandidate.create(
            tenant_id=tenant_id,
            kind=kind,
            payload=payload,
            confidence=confidence,
            trigger_reason=trigger_reason,
            workspace_id=workspace_id,
            requester_id=requester_id,
            ttl_seconds=ttl_seconds or self._default_ttl,
            correlation_id=correlation_id,
            now=self._clock.now(),
        )
        await self._repo.add(candidate)
        await self._publish_created(candidate)
        return candidate

    # ── reads ──────────────────────────────────────────────────────────

    async def get(
        self, *, tenant_id: TenantId, candidate_id: EvolveCandidateId
    ) -> EvolveCandidate:
        cand = await self._repo.get(tenant_id=tenant_id, candidate_id=candidate_id)
        if cand is None:
            raise EvolveCandidateNotFound(
                f"candidate {candidate_id} not found",
                code="EVOLVE_CANDIDATE_NOT_FOUND",
                details={"candidate_id": str(candidate_id)},
            )
        return cand

    async def list_pending(
        self, *, tenant_id: TenantId, limit: int = 200
    ) -> list[EvolveCandidate]:
        return await self._repo.list_pending(
            tenant_id=tenant_id, now=self._clock.now(), limit=limit
        )

    async def list_by_status(
        self,
        *,
        tenant_id: TenantId,
        status: EvolveStatus,
        limit: int = 100,
    ) -> list[EvolveCandidate]:
        return await self._repo.list_by_status(
            tenant_id=tenant_id, status=status, limit=limit
        )

    # ── transitions ────────────────────────────────────────────────────

    async def approve(
        self,
        *,
        tenant_id: TenantId,
        candidate_id: EvolveCandidateId,
        approver_id: UserId,
    ) -> EvolveCandidate:
        cand = await self.get(tenant_id=tenant_id, candidate_id=candidate_id)
        self._ensure_pending(cand)
        self._ensure_not_expired(cand)
        decided = cand.approve(approver_id=approver_id, now=self._clock.now())
        await self._repo.update(decided)
        await self._publish_decided(decided, approver_id=approver_id)
        return decided

    async def reject(
        self,
        *,
        tenant_id: TenantId,
        candidate_id: EvolveCandidateId,
        approver_id: UserId,
        reason: str = "",
    ) -> EvolveCandidate:
        cand = await self.get(tenant_id=tenant_id, candidate_id=candidate_id)
        self._ensure_pending(cand)
        decided = cand.reject(approver_id=approver_id, now=self._clock.now())
        await self._repo.update(decided)
        await self._publish_decided(decided, approver_id=approver_id, reason=reason)
        return decided

    async def apply(
        self,
        *,
        tenant_id: TenantId,
        candidate_id: EvolveCandidateId,
    ) -> tuple[EvolveCandidate, ApplyOutcome]:
        cand = await self.get(tenant_id=tenant_id, candidate_id=candidate_id)
        self._ensure_not_expired(cand)
        if cand.status is not EvolveStatus.APPROVED:
            raise EvolveCandidateAlreadyDecided(
                f"candidate {cand.id} must be APPROVED to apply, got {cand.status.value}",
                code="EVOLVE_CANDIDATE_ALREADY_DECIDED",
            )
        outcome = await self._guard.apply(tenant_id=tenant_id, candidate=cand)
        applied = cand.mark_applied(now=self._clock.now())
        await self._repo.update(applied)
        await self._publish_applied(applied, outcome.summary)
        return applied, outcome

    async def expire_if_due(
        self,
        *,
        tenant_id: TenantId,
        candidate_id: EvolveCandidateId,
    ) -> EvolveCandidate | None:
        cand = await self.get(tenant_id=tenant_id, candidate_id=candidate_id)
        if is_terminal(cand.status):
            return None
        now = self._clock.now()
        if cand.expires_at > now:
            return None
        # Expiration forces REJECTED; we don't have a separate EXPIRED state.
        decided = cand.reject(approver_id=cand.requester_id or UserId(cand.id), now=now)
        await self._repo.update(decided)
        await self._publish_decided(
            decided,
            approver_id=decided.requester_id or approver_id_synthetic(cand),
            reason="expired",
        )
        return decided

    # ── helpers ────────────────────────────────────────────────────────

    def _ensure_pending(self, cand: EvolveCandidate) -> None:
        if cand.status is not EvolveStatus.PENDING:
            raise EvolveCandidateAlreadyDecided(
                f"candidate {cand.id} already {cand.status.value}",
                code="EVOLVE_CANDIDATE_ALREADY_DECIDED",
            )

    def _ensure_not_expired(self, cand: EvolveCandidate) -> None:
        if cand.expires_at <= self._clock.now():
            raise EvolveCandidateAlreadyDecided(
                f"candidate {cand.id} has expired",
                code="EVOLVE_CANDIDATE_ALREADY_DECIDED",
                details={"expires_at": cand.expires_at.isoformat()},
            )

    async def _publish_created(self, cand: EvolveCandidate) -> None:
        if self._publisher is None:
            return
        event = EvolutionCandidateCreated(
            candidate_id=cand.id,
            tenant_id=cand.tenant_id,
            requester_id=cand.requester_id,
            kind=cand.kind,
            confidence=cand.confidence,
            occurred_at=self._clock.now(),
        )
        await self._publisher.publish(
            event.topic,
            {
                "event_name": event.topic,
                "event_id": str(event.event_id),
                "tenant_id": str(event.tenant_id),
                "candidate_id": str(event.candidate_id),
                "requester_id": str(event.requester_id) if event.requester_id else None,
                "kind": event.kind.value,
                "confidence": event.confidence,
                "occurred_at": event.occurred_at.isoformat(),
            },
        )

    async def _publish_decided(
        self,
        cand: EvolveCandidate,
        *,
        approver_id: UserId,
        reason: str = "",
    ) -> None:
        if self._publisher is None:
            return
        event = EvolutionCandidateDecided(
            candidate_id=cand.id,
            tenant_id=cand.tenant_id,
            approver_id=approver_id,
            status=cand.status,
            occurred_at=self._clock.now(),
        )
        await self._publisher.publish(
            event.topic,
            {
                "event_name": event.topic,
                "event_id": str(event.event_id),
                "tenant_id": str(event.tenant_id),
                "candidate_id": str(event.candidate_id),
                "approver_id": str(event.approver_id),
                "status": event.status.value,
                "reason": reason,
                "occurred_at": event.occurred_at.isoformat(),
            },
        )

    async def _publish_applied(
        self,
        cand: EvolveCandidate,
        summary: dict[str, Any],
    ) -> None:
        if self._publisher is None:
            return
        event = EvolutionCandidateApplied(
            candidate_id=cand.id,
            tenant_id=cand.tenant_id,
            kind=cand.kind,
            summary={k: str(v) for k, v in summary.items()},
            occurred_at=self._clock.now(),
        )
        await self._publisher.publish(
            event.topic,
            {
                "event_name": event.topic,
                "event_id": str(event.event_id),
                "tenant_id": str(event.tenant_id),
                "candidate_id": str(event.candidate_id),
                "kind": event.kind.value,
                "summary": event.summary,
                "occurred_at": event.occurred_at.isoformat(),
            },
        )


def approver_id_synthetic(cand: EvolveCandidate) -> UserId:
    """Fallback approver when expiration fires without a real reviewer.

    The same UUID as the candidate id is good enough for an audit trail —
    the rejection is system-initiated, not user-initiated.
    """
    from uuid import UUID as _UUID

    return UserId(_UUID(str(cand.id)))


__all__ = ["EvolutionCandidateService"]
