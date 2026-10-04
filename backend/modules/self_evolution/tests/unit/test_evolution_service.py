"""Unit tests for EvolutionCandidateService."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from _self_evolution_unit_in_memory import (
    CapturingEventPublisher,
    FixedClock,
    InMemoryEvolutionCandidateRepository,
    Uuid4IdGenerator,
)

from qzdap.modules.self_evolution.application.apply_guard import (
    ApplyGuard,
    ApplyOutcome,
    DirectApplyGuard,
)
from qzdap.modules.self_evolution.application.evolution_service import (
    EvolutionCandidateService,
)
from qzdap.modules.self_evolution.domain.errors import (
    EvolveCandidateAlreadyDecided,
    EvolveCandidateNotFound,
)
from qzdap.modules.self_evolution.domain.value_objects import (
    EvolveKind,
    EvolveStatus,
)

TENANT = UUID(int=1)
WORKSPACE = UUID(int=2)
USER_REQ = UUID(int=10)
USER_ADMIN = UUID(int=11)


@pytest.fixture
def svc() -> EvolutionCandidateService:
    return EvolutionCandidateService(
        repo=InMemoryEvolutionCandidateRepository(),
        clock=FixedClock(),
        ids=Uuid4IdGenerator(),
        apply_guard=DirectApplyGuard(),
        publisher=CapturingEventPublisher(),
    )


def _payload() -> dict:
    return {"key": "alpha", "score": 0.9}


# ── create ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_persists_and_emits_event(svc: EvolutionCandidateService) -> None:
    cand = await svc.create(
        tenant_id=TENANT,  # type: ignore[arg-type]
        kind=EvolveKind.MEMORY_PROMOTE,
        payload=_payload(),
        confidence=0.7,
        trigger_reason="post-turn signal",
        workspace_id=WORKSPACE,  # type: ignore[arg-type]
        requester_id=USER_REQ,  # type: ignore[arg-type]
    )
    assert cand.status is EvolveStatus.PENDING
    assert cand.requester_id == USER_REQ  # type: ignore[arg-type]
    publisher = svc._publisher  # type: ignore[attr-defined]
    assert isinstance(publisher, CapturingEventPublisher)
    topics = [t for t, _ in publisher.events]
    assert "governance.evolution.candidate.created" in topics


@pytest.mark.asyncio
async def test_create_with_no_publisher_does_not_raise(
    svc: EvolutionCandidateService,
) -> None:
    svc_no_pub = EvolutionCandidateService(
        repo=InMemoryEvolutionCandidateRepository(),
        clock=FixedClock(),
        ids=Uuid4IdGenerator(),
        apply_guard=DirectApplyGuard(),
    )
    cand = await svc_no_pub.create(
        tenant_id=TENANT,  # type: ignore[arg-type]
        kind=EvolveKind.MEMORY_PROMOTE,
        payload=_payload(),
        confidence=0.5,
        trigger_reason="x",
    )
    assert cand.status is EvolveStatus.PENDING


# ── get ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_returns_persisted(svc: EvolutionCandidateService) -> None:
    cand = await svc.create(
        tenant_id=TENANT,
        kind=EvolveKind.MEMORY_PROMOTE,
        payload=_payload(),
        confidence=0.7,
        trigger_reason="x",
    )
    fetched = await svc.get(
        tenant_id=TENANT,
        candidate_id=cand.id,  # type: ignore[arg-type]
    )
    assert fetched.id == cand.id


@pytest.mark.asyncio
async def test_get_raises_not_found(svc: EvolutionCandidateService) -> None:
    with pytest.raises(EvolveCandidateNotFound):
        await svc.get(
            tenant_id=TENANT,  # type: ignore[arg-type]
            candidate_id=uuid4(),  # type: ignore[arg-type]
        )


@pytest.mark.asyncio
async def test_get_blocks_cross_tenant(svc: EvolutionCandidateService) -> None:
    cand = await svc.create(
        tenant_id=TENANT,
        kind=EvolveKind.MEMORY_PROMOTE,
        payload={},
        confidence=0.5,
        trigger_reason="x",
    )
    with pytest.raises(EvolveCandidateNotFound):
        await svc.get(
            tenant_id=UUID(int=999),  # type: ignore[arg-type]
            candidate_id=cand.id,  # type: ignore[arg-type]
        )


# ── approve ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_approve_moves_to_approved_and_emits(
    svc: EvolutionCandidateService,
) -> None:
    cand = await svc.create(
        tenant_id=TENANT,
        kind=EvolveKind.MEMORY_PROMOTE,
        payload=_payload(),
        confidence=0.7,
        trigger_reason="x",
        requester_id=USER_REQ,
    )
    decided = await svc.approve(
        tenant_id=TENANT,
        candidate_id=cand.id,
        approver_id=USER_ADMIN,  # type: ignore[arg-type]
    )
    assert decided.status is EvolveStatus.APPROVED
    publisher = svc._publisher  # type: ignore[attr-defined]
    topics = [t for t, _ in publisher.events]
    assert "governance.evolution.candidate.decided" in topics


@pytest.mark.asyncio
async def test_approve_rejects_when_signer_equals_requester(
    svc: EvolutionCandidateService,
) -> None:
    cand = await svc.create(
        tenant_id=TENANT,
        kind=EvolveKind.MEMORY_PROMOTE,
        payload=_payload(),
        confidence=0.7,
        trigger_reason="x",
        requester_id=USER_ADMIN,
    )
    from qzdap.modules.self_evolution.domain.errors import SignerMustDiffer

    with pytest.raises(SignerMustDiffer):
        await svc.approve(
            tenant_id=TENANT,
            candidate_id=cand.id,
            approver_id=USER_ADMIN,  # type: ignore[arg-type]
        )


@pytest.mark.asyncio
async def test_approve_rejects_double_decision(svc: EvolutionCandidateService) -> None:
    cand = await svc.create(
        tenant_id=TENANT,
        kind=EvolveKind.MEMORY_PROMOTE,
        payload=_payload(),
        confidence=0.7,
        trigger_reason="x",
    )
    await svc.approve(
        tenant_id=TENANT,
        candidate_id=cand.id,
        approver_id=USER_ADMIN,  # type: ignore[arg-type]
    )
    with pytest.raises(EvolveCandidateAlreadyDecided):
        await svc.approve(
            tenant_id=TENANT,
            candidate_id=cand.id,
            approver_id=UUID(int=12),  # type: ignore[arg-type]
        )


@pytest.mark.asyncio
async def test_approve_rejects_when_expired(svc: EvolutionCandidateService) -> None:
    cand = await svc.create(
        tenant_id=TENANT,
        kind=EvolveKind.MEMORY_PROMOTE,
        payload=_payload(),
        confidence=0.7,
        trigger_reason="x",
        ttl_seconds=60,
    )
    clock = svc._clock  # type: ignore[attr-defined]
    clock.advance(hours=1)
    with pytest.raises(EvolveCandidateAlreadyDecided):
        await svc.approve(
            tenant_id=TENANT,
            candidate_id=cand.id,
            approver_id=USER_ADMIN,  # type: ignore[arg-type]
        )


# ── reject ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_reject_terminates_candidate(svc: EvolutionCandidateService) -> None:
    cand = await svc.create(
        tenant_id=TENANT,
        kind=EvolveKind.MEMORY_PROMOTE,
        payload=_payload(),
        confidence=0.7,
        trigger_reason="x",
    )
    decided = await svc.reject(
        tenant_id=TENANT,
        candidate_id=cand.id,
        approver_id=USER_ADMIN,  # type: ignore[arg-type]
        reason="not relevant",
    )
    assert decided.status is EvolveStatus.REJECTED


@pytest.mark.asyncio
async def test_reject_after_approve_fails(svc: EvolutionCandidateService) -> None:
    cand = await svc.create(
        tenant_id=TENANT,
        kind=EvolveKind.MEMORY_PROMOTE,
        payload=_payload(),
        confidence=0.7,
        trigger_reason="x",
    )
    await svc.approve(
        tenant_id=TENANT,
        candidate_id=cand.id,
        approver_id=USER_ADMIN,  # type: ignore[arg-type]
    )
    with pytest.raises(EvolveCandidateAlreadyDecided):
        await svc.reject(
            tenant_id=TENANT,
            candidate_id=cand.id,
            approver_id=USER_ADMIN,  # type: ignore[arg-type]
        )


# ── apply ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_apply_calls_guard_and_marks_applied(
    svc: EvolutionCandidateService,
) -> None:
    cand = await svc.create(
        tenant_id=TENANT,
        kind=EvolveKind.MEMORY_PROMOTE,
        payload=_payload(),
        confidence=0.7,
        trigger_reason="x",
    )
    await svc.approve(
        tenant_id=TENANT,
        candidate_id=cand.id,
        approver_id=USER_ADMIN,  # type: ignore[arg-type]
    )
    applied, outcome = await svc.apply(
        tenant_id=TENANT,
        candidate_id=cand.id,  # type: ignore[arg-type]
    )
    assert applied.status is EvolveStatus.APPLIED
    assert outcome.summary["mode"] == "direct"


@pytest.mark.asyncio
async def test_apply_without_approve_fails(svc: EvolutionCandidateService) -> None:
    cand = await svc.create(
        tenant_id=TENANT,
        kind=EvolveKind.MEMORY_PROMOTE,
        payload=_payload(),
        confidence=0.7,
        trigger_reason="x",
    )
    with pytest.raises(EvolveCandidateAlreadyDecided):
        await svc.apply(
            tenant_id=TENANT,
            candidate_id=cand.id,  # type: ignore[arg-type]
        )


@pytest.mark.asyncio
async def test_apply_is_not_idempotent(svc: EvolutionCandidateService) -> None:
    cand = await svc.create(
        tenant_id=TENANT,
        kind=EvolveKind.MEMORY_PROMOTE,
        payload=_payload(),
        confidence=0.7,
        trigger_reason="x",
    )
    await svc.approve(
        tenant_id=TENANT,
        candidate_id=cand.id,
        approver_id=USER_ADMIN,  # type: ignore[arg-type]
    )
    await svc.apply(tenant_id=TENANT, candidate_id=cand.id)  # type: ignore[arg-type]
    with pytest.raises(EvolveCandidateAlreadyDecided):
        await svc.apply(tenant_id=TENANT, candidate_id=cand.id)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_apply_uses_custom_guard(svc: EvolutionCandidateService) -> None:
    cand = await svc.create(
        tenant_id=TENANT,
        kind=EvolveKind.MEMORY_PROMOTE,
        payload=_payload(),
        confidence=0.7,
        trigger_reason="x",
    )
    await svc.approve(
        tenant_id=TENANT,
        candidate_id=cand.id,
        approver_id=USER_ADMIN,  # type: ignore[arg-type]
    )

    class _CountingGuard(ApplyGuard):
        calls = 0

        async def apply(  # type: ignore[override]
            self, *, tenant_id: UUID, candidate
        ):
            _CountingGuard.calls += 1
            return ApplyOutcome(
                candidate_id=candidate.id,
                kind=candidate.kind,
                summary={"mode": "counting"},
            )

    svc._guard = _CountingGuard()  # type: ignore[attr-defined]
    applied, outcome = await svc.apply(
        tenant_id=TENANT,
        candidate_id=cand.id,  # type: ignore[arg-type]
    )
    assert applied.status is EvolveStatus.APPLIED
    assert _CountingGuard.calls == 1
    assert outcome.summary["mode"] == "counting"


# ── expire_if_due ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_expire_if_due_rejects_when_due(svc: EvolutionCandidateService) -> None:
    cand = await svc.create(
        tenant_id=TENANT,
        kind=EvolveKind.MEMORY_PROMOTE,
        payload=_payload(),
        confidence=0.7,
        trigger_reason="x",
        ttl_seconds=60,
    )
    clock = svc._clock  # type: ignore[attr-defined]
    clock.advance(hours=1)
    expired = await svc.expire_if_due(
        tenant_id=TENANT,
        candidate_id=cand.id,  # type: ignore[arg-type]
    )
    assert expired is not None
    assert expired.status is EvolveStatus.REJECTED


@pytest.mark.asyncio
async def test_expire_if_due_returns_none_when_not_due(
    svc: EvolutionCandidateService,
) -> None:
    cand = await svc.create(
        tenant_id=TENANT,
        kind=EvolveKind.MEMORY_PROMOTE,
        payload=_payload(),
        confidence=0.7,
        trigger_reason="x",
        ttl_seconds=3600,
    )
    result = await svc.expire_if_due(
        tenant_id=TENANT,
        candidate_id=cand.id,  # type: ignore[arg-type]
    )
    assert result is None


@pytest.mark.asyncio
async def test_expire_if_due_returns_none_when_already_terminal(
    svc: EvolutionCandidateService,
) -> None:
    cand = await svc.create(
        tenant_id=TENANT,
        kind=EvolveKind.MEMORY_PROMOTE,
        payload=_payload(),
        confidence=0.7,
        trigger_reason="x",
    )
    await svc.approve(
        tenant_id=TENANT,
        candidate_id=cand.id,
        approver_id=USER_ADMIN,  # type: ignore[arg-type]
    )
    result = await svc.expire_if_due(
        tenant_id=TENANT,
        candidate_id=cand.id,  # type: ignore[arg-type]
    )
    assert result is None


# ── list ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_pending_excludes_terminal_and_expired(
    svc: EvolutionCandidateService,
) -> None:
    a = await svc.create(
        tenant_id=TENANT,
        kind=EvolveKind.MEMORY_PROMOTE,
        payload={"k": "a"},
        confidence=0.5,
        trigger_reason="x",
        ttl_seconds=3600,
    )
    b = await svc.create(
        tenant_id=TENANT,
        kind=EvolveKind.SKILL_PATCH,
        payload={"k": "b"},
        confidence=0.5,
        trigger_reason="x",
        ttl_seconds=60,
    )
    await svc.reject(
        tenant_id=TENANT,
        candidate_id=a.id,
        approver_id=USER_ADMIN,  # type: ignore[arg-type]
    )
    svc._clock.advance(hours=1)  # type: ignore[attr-defined]
    pending = await svc.list_pending(tenant_id=TENANT, limit=100)  # type: ignore[arg-type]
    assert all(c.status is EvolveStatus.PENDING for c in pending)
    assert all(c.expires_at > svc._clock.now() for c in pending)  # type: ignore[attr-defined]
    assert b.id not in [c.id for c in pending]


@pytest.mark.asyncio
async def test_list_by_status_filters_correctly(svc: EvolutionCandidateService) -> None:
    cand = await svc.create(
        tenant_id=TENANT,
        kind=EvolveKind.MEMORY_PROMOTE,
        payload={},
        confidence=0.5,
        trigger_reason="x",
    )
    await svc.approve(
        tenant_id=TENANT,
        candidate_id=cand.id,
        approver_id=USER_ADMIN,  # type: ignore[arg-type]
    )
    approved = await svc.list_by_status(
        tenant_id=TENANT,
        status=EvolveStatus.APPROVED,  # type: ignore[arg-type]
    )
    assert cand.id in [c.id for c in approved]
    pending = await svc.list_by_status(
        tenant_id=TENANT,
        status=EvolveStatus.PENDING,  # type: ignore[arg-type]
    )
    assert cand.id not in [c.id for c in pending]


# ── cross-tenant ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cross_tenant_list_isolated(svc: EvolutionCandidateService) -> None:
    cand_t1 = await svc.create(
        tenant_id=TENANT,
        kind=EvolveKind.MEMORY_PROMOTE,
        payload={},
        confidence=0.5,
        trigger_reason="x",
    )
    cand_t2 = await svc.create(
        tenant_id=UUID(int=999),
        kind=EvolveKind.MEMORY_PROMOTE,
        payload={},  # type: ignore[arg-type]
        confidence=0.5,
        trigger_reason="x",
    )
    pending_t1 = await svc.list_pending(tenant_id=TENANT, limit=100)  # type: ignore[arg-type]
    assert cand_t1.id in [c.id for c in pending_t1]
    assert cand_t2.id not in [c.id for c in pending_t1]


@pytest.mark.asyncio
async def test_event_published_for_applied(svc: EvolutionCandidateService) -> None:
    cand = await svc.create(
        tenant_id=TENANT,
        kind=EvolveKind.MEMORY_PROMOTE,
        payload={},
        confidence=0.5,
        trigger_reason="x",
    )
    await svc.approve(
        tenant_id=TENANT,
        candidate_id=cand.id,
        approver_id=USER_ADMIN,  # type: ignore[arg-type]
    )
    await svc.apply(tenant_id=TENANT, candidate_id=cand.id)  # type: ignore[arg-type]
    publisher = svc._publisher  # type: ignore[attr-defined]
    topics = [t for t, _ in publisher.events]
    assert "governance.evolution.candidate.applied" in topics
