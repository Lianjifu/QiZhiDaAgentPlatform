"""Unit tests for EvolveCandidate entity + value objects."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from qzdap.modules.self_evolution.domain.entities import (
    EvolveCandidate,
    compute_fingerprint,
)
from qzdap.modules.self_evolution.domain.errors import (
    EvolveCandidateAlreadyDecided,
    InvalidEvolveCandidate,
    SignerMustDiffer,
)
from qzdap.modules.self_evolution.domain.value_objects import (
    EvolveKind,
    EvolveStatus,
    is_terminal,
)

TENANT = UUID(int=1)
WORKSPACE = UUID(int=2)
USER_REQ = UUID(int=10)
USER_ADMIN = UUID(int=11)


def _candidate(
    *,
    requester_id: UUID | None = USER_REQ,
    confidence: float = 0.7,
    trigger_reason: str = "post-turn signal",
) -> EvolveCandidate:
    return EvolveCandidate.create(
        tenant_id=TENANT,  # type: ignore[arg-type]
        kind=EvolveKind.MEMORY_PROMOTE,
        payload={"key": "alpha", "score": 0.9},
        confidence=confidence,
        trigger_reason=trigger_reason,
        workspace_id=WORKSPACE,  # type: ignore[arg-type]
        requester_id=requester_id,  # type: ignore[arg-type]
    )


# ── value_objects ──────────────────────────────────────────────────────


def test_is_terminal_table() -> None:
    assert is_terminal(EvolveStatus.REJECTED)
    assert is_terminal(EvolveStatus.APPLIED)
    assert not is_terminal(EvolveStatus.PENDING)
    assert not is_terminal(EvolveStatus.APPROVED)


def test_evolve_kind_str_values() -> None:
    assert EvolveKind.MEMORY_PROMOTE.value == "memory_promote"
    assert EvolveKind.SKILL_PATCH.value == "skill_patch"
    assert EvolveKind.ROUTING_HINT.value == "routing_hint"
    assert EvolveKind.DREAM.value == "dream"


# ── compute_fingerprint ───────────────────────────────────────────────


def test_fingerprint_is_sha256_hex_64() -> None:
    fp = compute_fingerprint(
        tenant_id=TENANT,  # type: ignore[arg-type]
        kind=EvolveKind.MEMORY_PROMOTE,
        payload={"a": 1, "b": 2},
    )
    assert len(fp) == 64
    int(fp, 16)  # raises if not hex


def test_fingerprint_is_deterministic_and_canonical() -> None:
    a = compute_fingerprint(
        tenant_id=TENANT,
        kind=EvolveKind.MEMORY_PROMOTE,
        payload={"a": 1, "b": 2},  # type: ignore[arg-type]
    )
    b = compute_fingerprint(
        tenant_id=TENANT,
        kind=EvolveKind.MEMORY_PROMOTE,
        payload={"b": 2, "a": 1},  # type: ignore[arg-type]
    )
    assert a == b


def test_fingerprint_differs_by_tenant_and_kind_and_payload() -> None:
    base = compute_fingerprint(
        tenant_id=TENANT,
        kind=EvolveKind.MEMORY_PROMOTE,
        payload={"x": 1},  # type: ignore[arg-type]
    )
    other_tenant = compute_fingerprint(
        tenant_id=UUID(int=999),
        kind=EvolveKind.MEMORY_PROMOTE,
        payload={"x": 1},  # type: ignore[arg-type]
    )
    other_kind = compute_fingerprint(
        tenant_id=TENANT,
        kind=EvolveKind.SKILL_PATCH,
        payload={"x": 1},  # type: ignore[arg-type]
    )
    other_payload = compute_fingerprint(
        tenant_id=TENANT,
        kind=EvolveKind.MEMORY_PROMOTE,
        payload={"x": 2},  # type: ignore[arg-type]
    )
    assert base != other_tenant
    assert base != other_kind
    assert base != other_payload


# ── create() ──────────────────────────────────────────────────────────


def test_create_assigns_pending_status_and_expiry() -> None:
    cand = _candidate()
    assert cand.status is EvolveStatus.PENDING
    assert cand.expires_at > cand.created_at


def test_create_rejects_confidence_out_of_range() -> None:
    with pytest.raises(InvalidEvolveCandidate):
        EvolveCandidate.create(
            tenant_id=TENANT,  # type: ignore[arg-type]
            kind=EvolveKind.MEMORY_PROMOTE,
            payload={},
            confidence=1.5,
            trigger_reason="x",
        )
    with pytest.raises(InvalidEvolveCandidate):
        EvolveCandidate.create(
            tenant_id=TENANT,  # type: ignore[arg-type]
            kind=EvolveKind.MEMORY_PROMOTE,
            payload={},
            confidence=-0.01,
            trigger_reason="x",
        )


def test_create_rejects_blank_trigger_reason() -> None:
    with pytest.raises(InvalidEvolveCandidate):
        _candidate(trigger_reason="   ")
    with pytest.raises(InvalidEvolveCandidate):
        _candidate(trigger_reason="")


def test_create_rejects_too_long_trigger_reason() -> None:
    with pytest.raises(InvalidEvolveCandidate):
        _candidate(trigger_reason="a" * 257)


def test_create_rejects_zero_ttl() -> None:
    with pytest.raises(InvalidEvolveCandidate):
        EvolveCandidate.create(
            tenant_id=TENANT,  # type: ignore[arg-type]
            kind=EvolveKind.MEMORY_PROMOTE,
            payload={},
            confidence=0.5,
            trigger_reason="ok",
            ttl_seconds=0,
        )


def test_create_supports_no_requester() -> None:
    cand = _candidate(requester_id=None)
    assert cand.requester_id is None


# ── approve() ─────────────────────────────────────────────────────────


def test_approve_moves_to_approved_with_admin() -> None:
    cand = _candidate()
    decided = cand.approve(approver_id=USER_ADMIN)  # type: ignore[arg-type]
    assert decided.status is EvolveStatus.APPROVED
    assert decided.approver_id == USER_ADMIN  # type: ignore[arg-type]
    assert decided.reviewed_at is not None


def test_approve_rejects_when_requester_equals_admin() -> None:
    cand = _candidate(requester_id=USER_ADMIN)
    with pytest.raises(SignerMustDiffer):
        cand.approve(approver_id=USER_ADMIN)  # type: ignore[arg-type]


def test_approve_rejects_double_decision() -> None:
    cand = _candidate()
    approved = cand.approve(approver_id=USER_ADMIN)  # type: ignore[arg-type]
    with pytest.raises(EvolveCandidateAlreadyDecided):
        approved.approve(approver_id=UUID(int=12))  # type: ignore[arg-type]


def test_approve_when_no_requester_does_not_require_differ() -> None:
    # No requester means the candidate is system-generated; admin can
    # sign any way without the SignerMustDiffer rule triggering.
    cand = _candidate(requester_id=None)
    decided = cand.approve(approver_id=USER_ADMIN)  # type: ignore[arg-type]
    assert decided.status is EvolveStatus.APPROVED


# ── reject() ──────────────────────────────────────────────────────────


def test_reject_moves_to_rejected() -> None:
    cand = _candidate()
    decided = cand.reject(approver_id=USER_ADMIN)  # type: ignore[arg-type]
    assert decided.status is EvolveStatus.REJECTED


def test_reject_rejects_double_decision() -> None:
    cand = _candidate()
    rejected = cand.reject(approver_id=USER_ADMIN)  # type: ignore[arg-type]
    with pytest.raises(EvolveCandidateAlreadyDecided):
        rejected.approve(approver_id=UUID(int=12))  # type: ignore[arg-type]


# ── mark_applied() ────────────────────────────────────────────────────


def test_mark_applied_only_after_approved() -> None:
    cand = _candidate()
    with pytest.raises(EvolveCandidateAlreadyDecided):
        cand.mark_applied()
    approved = cand.approve(approver_id=USER_ADMIN)  # type: ignore[arg-type]
    applied = approved.mark_applied()
    assert applied.status is EvolveStatus.APPLIED
    assert applied.applied_at is not None


def test_mark_applied_is_idempotent_only_via_raise() -> None:
    cand = _candidate()
    approved = cand.approve(approver_id=USER_ADMIN)  # type: ignore[arg-type]
    applied = approved.mark_applied()
    with pytest.raises(EvolveCandidateAlreadyDecided):
        applied.mark_applied()


# ── fingerprint propagation ───────────────────────────────────────────


def test_fingerprint_propagates_from_create_to_update() -> None:
    cand = _candidate()
    approved = cand.approve(approver_id=USER_ADMIN)  # type: ignore[arg-type]
    applied = approved.mark_applied()
    assert applied.fingerprint == cand.fingerprint


_ = uuid4  # silence unused-import warnings in this test file
