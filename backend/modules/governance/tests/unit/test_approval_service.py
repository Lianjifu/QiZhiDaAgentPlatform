"""Tests for ``Approval`` state machine + ``ApprovalService``."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from _governance_unit_in_memory import (
    FixedClock,
    InMemoryApprovalRepository,
    RecordingPublisher,
    SequenceIds,
)

from qzdap.modules.governance.application.approval_service import ApprovalService
from qzdap.modules.governance.domain.entities import Approval
from qzdap.modules.governance.domain.errors import (
    ApprovalAlreadyDecided,
    ApprovalExpired,
    ApproverMustDiffer,
)
from qzdap.modules.governance.domain.value_objects import ApprovalStatus
from qzdap_kernel.ids import TenantId, UserId

TID = TenantId(UUID("00000000-0000-0000-0000-000000000001"))
USER_A = UserId(UUID("00000000-0000-0000-0000-00000000000a"))
USER_B = UserId(UUID("00000000-0000-0000-0000-00000000000b"))


def _service() -> tuple[
    ApprovalService, InMemoryApprovalRepository, RecordingPublisher, FixedClock
]:
    repo = InMemoryApprovalRepository()
    pub = RecordingPublisher()
    clock = FixedClock()
    ids = SequenceIds()
    svc = ApprovalService(
        repo=repo,
        clock=clock,
        ids=ids,
        publisher=pub,
        default_ttl_seconds=3600,
    )
    return svc, repo, pub, clock


async def test_create_starts_pending_and_publishes_event():
    svc, _, pub, clock = _service()
    ap = await svc.create(
        tenant_id=TID,
        requester_id=USER_A,
        action="tool:execute:reverse",
        resource={"tool": "reverse"},
    )
    assert ap.status is ApprovalStatus.PENDING
    assert ap.expires_at > clock.now()
    assert any(t == "governance.approval.requested" for t, _ in pub.published)


async def test_approve_happy_path():
    svc, _repo, pub, _ = _service()
    ap = await svc.create(
        tenant_id=TID,
        requester_id=USER_A,
        action="tool:execute:reverse",
        resource={"tool": "reverse"},
    )
    decided = await svc.approve(
        tenant_id=TID,
        approval_id=ap.id,
        approver_id=USER_B,  # type: ignore[arg-type]
    )
    assert decided.status is ApprovalStatus.APPROVED
    assert decided.approver_id == USER_B
    assert any(t == "governance.approval.decided" for t, _ in pub.published)


async def test_approve_same_actor_as_requester_rejected():
    svc, _, _, _ = _service()
    ap = await svc.create(
        tenant_id=TID,
        requester_id=USER_A,
        action="tool:execute:reverse",
        resource={},
    )
    import pytest

    with pytest.raises(ApproverMustDiffer):
        await svc.approve(
            tenant_id=TID,
            approval_id=ap.id,
            approver_id=USER_A,  # type: ignore[arg-type]
        )


async def test_approve_already_decided_rejected():
    svc, _, _, _ = _service()
    ap = await svc.create(
        tenant_id=TID,
        requester_id=USER_A,
        action="tool:execute:reverse",
        resource={},
    )
    await svc.approve(
        tenant_id=TID,
        approval_id=ap.id,
        approver_id=USER_B,  # type: ignore[arg-type]
    )
    import pytest

    with pytest.raises(ApprovalAlreadyDecided):
        await svc.approve(
            tenant_id=TID,
            approval_id=ap.id,
            approver_id=USER_B,  # type: ignore[arg-type]
        )


async def test_deny_records_reason_in_payload():
    svc, _repo, _, _ = _service()
    ap = await svc.create(
        tenant_id=TID,
        requester_id=USER_A,
        action="tool:execute:reverse",
        resource={},
    )
    decided = await svc.deny(
        tenant_id=TID,
        approval_id=ap.id,  # type: ignore[arg-type]
        approver_id=USER_B,
        reason="not authorized",
    )
    assert decided.status is ApprovalStatus.DENIED
    assert decided.payload["deny_reason"] == "not authorized"


async def test_expire_if_due_returns_expired_when_past():
    svc, _, _, clock = _service()
    ap = await svc.create(
        tenant_id=TID,
        requester_id=USER_A,
        action="tool:execute:reverse",
        resource={},
    )
    # Advance past expiry
    clock.advance(seconds=3601)
    expired = await svc.expire_if_due(
        tenant_id=TID,
        approval_id=ap.id,  # type: ignore[arg-type]
    )
    assert expired is not None
    assert expired.status is ApprovalStatus.EXPIRED


async def test_expire_if_due_no_op_when_not_due():
    svc, _, _, _ = _service()
    ap = await svc.create(
        tenant_id=TID,
        requester_id=USER_A,
        action="tool:execute:reverse",
        resource={},
    )
    res = await svc.expire_if_due(
        tenant_id=TID,
        approval_id=ap.id,  # type: ignore[arg-type]
    )
    assert res is None


async def test_approve_after_expiry_rejected():
    svc, _, _, clock = _service()
    ap = await svc.create(
        tenant_id=TID,
        requester_id=USER_A,
        action="tool:execute:reverse",
        resource={},
    )
    clock.advance(seconds=3601)
    import pytest

    with pytest.raises(ApprovalExpired):
        await svc.approve(
            tenant_id=TID,
            approval_id=ap.id,
            approver_id=USER_B,  # type: ignore[arg-type]
        )


async def test_approval_entity_returns_new_instance():
    """Mutation methods return new Approval; original is unchanged."""
    ap = Approval.create(
        tenant_id=TID,
        requester_id=USER_A,
        action="tool:execute:reverse",
        resource={"k": "v"},
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    approved = ap.approve(approver_id=USER_B)
    assert ap.status is ApprovalStatus.PENDING
    assert approved.status is ApprovalStatus.APPROVED
    assert ap is not approved


async def test_list_all_returns_every_status_in_newest_first_order():
    """list_all fans out across every ApprovalStatus and dedupes.

    Regression for the prior bug where ``GET /v1/approvals?
    pending_only=false`` silently filtered to PENDING — admins got
    empty history pages even when there were APPROVED / DENIED rows.
    """
    svc, _repo, _pub, clock = _service()
    a = await svc.create(
        tenant_id=TID,
        requester_id=USER_A,
        action="tool:execute:reverse",
        resource={"k": 1},
    )
    clock.advance(seconds=60)
    b = await svc.create(
        tenant_id=TID,
        requester_id=USER_A,
        action="tool:execute:reverse",
        resource={"k": 2},
    )
    clock.advance(seconds=60)
    await svc.approve(tenant_id=TID, approval_id=a.id, approver_id=USER_B)
    clock.advance(seconds=60)
    await svc.deny(tenant_id=TID, approval_id=b.id, approver_id=USER_B, reason="nope")

    rows = await svc.list_all(tenant_id=TID, limit=10)
    statuses = [r.status for r in rows]
    # Both decided rows must be present — the prior bug filtered
    # everything to PENDING.
    assert ApprovalStatus.APPROVED in statuses
    assert ApprovalStatus.DENIED in statuses
    # Newest first.
    assert rows[0].created_at >= rows[-1].created_at


async def test_list_all_respects_limit():
    svc, _repo, _pub, _clock = _service()
    for i in range(5):
        await svc.create(
            tenant_id=TID,
            requester_id=USER_A,
            action="tool:execute:reverse",
            resource={"i": i},
        )
    rows = await svc.list_all(tenant_id=TID, limit=3)
    assert len(rows) == 3


async def test_the_same_correlation_id_reuses_the_approval():
    """**审批幂等** ✓（Session 方案 S-31 ✓）—— 重试**不多出一条待办** ✓。"""
    svc, repo, _pub, _clock = _service()
    correlation_id = UUID("00000000-0000-0000-0000-0000000000c1")
    first = await svc.create(
        tenant_id=TID,
        requester_id=USER_A,
        action="agent.tool.sandbox_exec",
        resource={"tool": "sandbox_exec"},
        correlation_id=correlation_id,
    )
    second = await svc.create(
        tenant_id=TID,
        requester_id=USER_A,
        action="agent.tool.sandbox_exec",
        resource={"tool": "sandbox_exec"},
        correlation_id=correlation_id,
    )
    assert second.id == first.id
    assert len(repo._rows) == 1


async def test_the_due_approvals_are_expired_by_the_sweep():
    """**到期未决策 → 自动过期** ✓（Session 方案 §3.3 第 2 类 ✓）。"""
    svc, _repo, _pub, clock = _service()
    await svc.create(
        tenant_id=TID,
        requester_id=USER_A,
        action="agent.tool.sandbox_exec",
        resource={"tool": "sandbox_exec"},
        ttl_seconds=60,
    )
    # ⚠️ **时间往前推** ✓（超过 TTL ✓）。
    clock.advance(120)
    expired = await svc.expire_due(now=clock.now())
    assert expired == 1
    pending = await svc.list_pending(tenant_id=TID)
    assert pending == []
