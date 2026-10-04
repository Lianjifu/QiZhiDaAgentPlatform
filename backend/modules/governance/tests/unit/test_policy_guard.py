"""Tests for ``PolicyGuard`` — the entry-point decorator for use cases."""

from __future__ import annotations

from uuid import UUID

from _governance_unit_in_memory import (
    FixedClock,
    InMemoryApprovalRepository,
    InMemoryDecisionEventRepo,
    InMemoryPolicyRepository,
    RecordingPublisher,
    SequenceIds,
)
from qzdap_kernel.errors import ActionDeniedError, ApprovalRequiredError
from qzdap_schema.ids import TenantId, UserId
from qzdap_vault.actor import ActorContext

from qzdap.modules.governance.adapter.guard.policy_guard import PolicyGuard
from qzdap.modules.governance.application.policy_evaluator import PolicyEvaluator
from qzdap.modules.governance.domain.entities import PolicyRule
from qzdap.modules.governance.domain.value_objects import PolicyEffect, PolicySubject

TID = TenantId(UUID("00000000-0000-0000-0000-000000000001"))
USER = UserId(UUID("00000000-0000-0000-0000-00000000000a"))


def _actor() -> ActorContext:
    return ActorContext(
        tenant_id=TID,
        workspace_id=None,
        principal_id=USER,
        roles=frozenset({"workspace_member"}),
    )


def _guard_with_rule(rule: PolicyRule | None) -> PolicyGuard:
    repo = InMemoryPolicyRepository()
    ap_repo = InMemoryApprovalRepository()
    dec = InMemoryDecisionEventRepo()
    if rule is not None:
        # PolicyRule.create needs dataclass; this helper accepts a prebuilt
        # entity.  Just add it.
        pass
    from asyncio import get_event_loop  # noqa: F401  (avoid unused import linter)

    return PolicyGuard(
        evaluator=PolicyEvaluator(
            policy_repo=repo,
            approval_repo=ap_repo,
            decision_repo=dec,
            clock=FixedClock(),
            ids=SequenceIds(),
            publisher=RecordingPublisher(),
        )
    )


async def test_check_allow_passes_silently():
    # default allow when no rule matches
    g = _guard_with_rule(None)
    rec = await g.check(actor=_actor(), action="tool:execute:reverse", resource={})
    assert rec.effect is PolicyEffect.ALLOW


async def test_check_deny_raises_action_denied():
    from qzdap.modules.governance.domain.entities import PolicyRule
    from qzdap.modules.governance.domain.value_objects import PolicySubject

    deny_rule = PolicyRule.create(
        tenant_id=TID,
        subject_type=PolicySubject.ROLE,
        subject_ref="workspace_member",
        action_pattern="tool:execute:reverse",
        effect=PolicyEffect.DENY,
    )
    g = _guard_with_rule(deny_rule)
    # Add rule to the underlying repo by reaching through the guard's evaluator.
    await g._evaluator._policies.add(deny_rule)  # type: ignore[attr-defined]
    g._evaluator.invalidate(tenant_id=TID)  # type: ignore[attr-defined]

    import pytest

    with pytest.raises(ActionDeniedError) as ei:
        await g.check(actor=_actor(), action="tool:execute:reverse", resource={})
    assert ei.value.code == "ACTION_DENIED"
    assert "matched rule" in ei.value.reason


async def test_check_approval_raises_approval_required():
    from qzdap.modules.governance.domain.entities import PolicyRule

    ap_rule = PolicyRule.create(
        tenant_id=TID,
        subject_type=PolicySubject.ROLE,
        subject_ref="workspace_member",
        action_pattern="tool:execute:clock",
        effect=PolicyEffect.REQUIRE_APPROVAL,
    )
    g = _guard_with_rule(ap_rule)
    await g._evaluator._policies.add(ap_rule)  # type: ignore[attr-defined]
    g._evaluator.invalidate(tenant_id=TID)  # type: ignore[attr-defined]

    import pytest

    with pytest.raises(ApprovalRequiredError) as ei:
        await g.check(actor=_actor(), action="tool:execute:clock", resource={})
    assert ei.value.code == "APPROVAL_REQUIRED"
    assert ei.value.details.get("approval_id") is not None


async def test_check_approval_error_has_202_status():
    from qzdap.modules.governance.domain.entities import PolicyRule

    ap_rule = PolicyRule.create(
        tenant_id=TID,
        subject_type=PolicySubject.ROLE,
        subject_ref="workspace_member",
        action_pattern="tool:execute:clock",
        effect=PolicyEffect.REQUIRE_APPROVAL,
    )
    g = _guard_with_rule(ap_rule)
    await g._evaluator._policies.add(ap_rule)  # type: ignore[attr-defined]
    g._evaluator.invalidate(tenant_id=TID)  # type: ignore[attr-defined]

    import pytest

    with pytest.raises(ApprovalRequiredError) as ei:
        await g.check(actor=_actor(), action="tool:execute:clock", resource={})
    assert ei.value.status == 202
