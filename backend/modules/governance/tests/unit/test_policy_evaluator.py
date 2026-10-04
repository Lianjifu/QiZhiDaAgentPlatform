"""Tests for ``PolicyEvaluator``.

Covers:
- default allow when no rule matches
- matched ALLOW wins
- matched DENY beats matched ALLOW (precedence)
- matched REQUIRE_APPROVAL mints an Approval and returns it
- same precedence ⇒ priority ASC tiebreak
- TTL cache: re-fetch skipped on second call
- cache invalidation forces re-fetch
- decision_events always recorded
"""

from __future__ import annotations

from uuid import UUID, uuid4

from _governance_unit_in_memory import (
    FixedClock,
    InMemoryApprovalRepository,
    InMemoryDecisionEventRepo,
    InMemoryPolicyRepository,
    RecordingPublisher,
    SequenceIds,
)
from qzdap_schema.ids import TenantId
from qzdap_vault.actor import ActorContext

from qzdap.modules.governance.application.policy_evaluator import PolicyEvaluator
from qzdap.modules.governance.domain.entities import PolicyRule
from qzdap.modules.governance.domain.value_objects import PolicyEffect, PolicySubject

TID = TenantId(UUID("00000000-0000-0000-0000-000000000001"))
USER = UUID("00000000-0000-0000-0000-00000000000a")


def _actor(*, roles=("workspace_member",)) -> ActorContext:
    return ActorContext(
        tenant_id=TID,
        workspace_id=None,
        principal_id=USER,
        roles=frozenset(roles),
    )


def _evaluator() -> tuple[
    PolicyEvaluator,
    InMemoryPolicyRepository,
    InMemoryApprovalRepository,
    InMemoryDecisionEventRepo,
    RecordingPublisher,
]:
    repo = InMemoryPolicyRepository()
    ap_repo = InMemoryApprovalRepository()
    dec = InMemoryDecisionEventRepo()
    clock = FixedClock()
    ids = SequenceIds()
    pub = RecordingPublisher()
    ev = PolicyEvaluator(
        policy_repo=repo,
        approval_repo=ap_repo,
        decision_repo=dec,
        clock=clock,
        ids=ids,
        publisher=pub,
        cache_ttl_seconds=30,
    )
    return ev, repo, ap_repo, dec, pub


async def test_evaluate_no_rules_default_allow():
    ev, _, _, dec, _ = _evaluator()
    rec = await ev.evaluate(actor=_actor(), action="tool:execute:reverse", resource={})
    assert rec.effect is PolicyEffect.ALLOW
    assert rec.rule_id is None
    # decision_event still recorded for audit
    assert len(dec.events) == 1
    assert dec.events[0].effect is PolicyEffect.ALLOW


async def test_evaluate_allow_match():
    ev, repo, _, dec, _ = _evaluator()
    rule = PolicyRule.create(
        tenant_id=TID,
        subject_type=PolicySubject.ROLE,
        subject_ref="workspace_member",
        action_pattern="tool:execute:reverse",
        effect=PolicyEffect.ALLOW,
    )
    await repo.add(rule)
    rec = await ev.evaluate(actor=_actor(), action="tool:execute:reverse", resource={})
    assert rec.effect is PolicyEffect.ALLOW
    assert rec.rule_id == rule.id
    assert len(dec.events) == 1


async def test_evaluate_deny_beats_allow():
    ev, repo, _, _dec, _ = _evaluator()
    allow = PolicyRule.create(
        tenant_id=TID,
        subject_type=PolicySubject.ROLE,
        subject_ref="workspace_member",
        action_pattern="tool:*",
        effect=PolicyEffect.ALLOW,
        priority=100,
    )
    deny = PolicyRule.create(
        tenant_id=TID,
        subject_type=PolicySubject.ROLE,
        subject_ref="workspace_member",
        action_pattern="tool:execute:reverse",
        effect=PolicyEffect.DENY,
        priority=50,
    )
    await repo.add(allow)
    await repo.add(deny)
    rec = await ev.evaluate(actor=_actor(), action="tool:execute:reverse", resource={})
    assert rec.effect is PolicyEffect.DENY
    assert rec.rule_id == deny.id


async def test_evaluate_approval_mints_approval_record():
    ev, repo, ap_repo, _, pub = _evaluator()
    rule = PolicyRule.create(
        tenant_id=TID,
        subject_type=PolicySubject.ROLE,
        subject_ref="workspace_member",
        action_pattern="tool:execute:clock",
        effect=PolicyEffect.REQUIRE_APPROVAL,
    )
    await repo.add(rule)
    rec = await ev.evaluate(actor=_actor(), action="tool:execute:clock", resource={})
    assert rec.effect is PolicyEffect.REQUIRE_APPROVAL
    assert rec.approval_id is not None
    approval = await ap_repo.get(
        tenant_id=TID,
        approval_id=rec.approval_id,  # type: ignore[arg-type]
    )
    assert approval is not None
    assert approval.action == "tool:execute:clock"
    # publisher saw the requested event
    assert any(t == "governance.approval.requested" for t, _ in pub.published)


async def test_evaluate_same_priority_priority_asc_tiebreak():
    ev, repo, _, _, _ = _evaluator()
    high = PolicyRule.create(
        tenant_id=TID,
        subject_type=PolicySubject.ROLE,
        subject_ref="workspace_member",
        action_pattern="tool:execute:reverse",
        effect=PolicyEffect.DENY,
        priority=10,
    )
    low = PolicyRule.create(
        tenant_id=TID,
        subject_type=PolicySubject.ROLE,
        subject_ref="workspace_member",
        action_pattern="tool:execute:reverse",
        effect=PolicyEffect.DENY,
        priority=90,
    )
    await repo.add(low)
    await repo.add(high)
    rec = await ev.evaluate(actor=_actor(), action="tool:execute:reverse", resource={})
    assert rec.rule_id == high.id


async def test_evaluate_cache_ttl_hits():
    ev, repo, _, dec, _ = _evaluator()
    rule = PolicyRule.create(
        tenant_id=TID,
        subject_type=PolicySubject.ROLE,
        subject_ref="workspace_member",
        action_pattern="tool:*",
        effect=PolicyEffect.ALLOW,
    )
    await repo.add(rule)
    await ev.evaluate(actor=_actor(), action="tool:execute:reverse", resource={})
    # mutate repo directly — without invalidate, cache still serves stale
    # snapshot.  Add another rule and call again — cache hit ⇒ only 1 event.
    await repo.add(
        PolicyRule.create(
            tenant_id=TID,
            subject_type=PolicySubject.ROLE,
            subject_ref="workspace_member",
            action_pattern="tool:execute:reverse",
            effect=PolicyEffect.DENY,
        )
    )
    rec = await ev.evaluate(actor=_actor(), action="tool:execute:reverse", resource={})
    assert rec.effect is PolicyEffect.ALLOW  # served from cache
    assert len(dec.events) == 2


async def test_evaluate_invalidate_forces_refetch():
    ev, repo, _, _, _ = _evaluator()
    await repo.add(
        PolicyRule.create(
            tenant_id=TID,
            subject_type=PolicySubject.ROLE,
            subject_ref="workspace_member",
            action_pattern="tool:execute:reverse",
            effect=PolicyEffect.ALLOW,
        )
    )
    rec1 = await ev.evaluate(actor=_actor(), action="tool:execute:reverse", resource={})
    assert rec1.effect is PolicyEffect.ALLOW

    # flip the rule to deny, then invalidate — second call should see deny
    row = next(iter(await repo.list_records(tenant_id=TID)))
    from dataclasses import replace

    await repo.update(replace(row, effect=PolicyEffect.DENY))
    ev.invalidate(tenant_id=TID)

    rec2 = await ev.evaluate(actor=_actor(), action="tool:execute:reverse", resource={})
    assert rec2.effect is PolicyEffect.DENY


async def test_evaluate_disabled_rule_ignored():
    ev, repo, _, _, _ = _evaluator()
    rule = PolicyRule.create(
        tenant_id=TID,
        subject_type=PolicySubject.ROLE,
        subject_ref="workspace_member",
        action_pattern="tool:*",
        effect=PolicyEffect.DENY,
        enabled=False,
    )
    await repo.add(rule)
    rec = await ev.evaluate(actor=_actor(), action="tool:execute:reverse", resource={})
    assert rec.effect is PolicyEffect.ALLOW  # default allow
    assert rec.rule_id is None


async def test_evaluate_workspace_scoped_rule_filters():
    """Rule pinned to workspace A must not match resource carrying workspace B."""
    from qzdap_schema.ids import WorkspaceId

    ev, repo, _, _, _ = _evaluator()
    a = WorkspaceId(uuid4())
    b = WorkspaceId(uuid4())
    rule = PolicyRule.create(
        tenant_id=TID,
        subject_type=PolicySubject.ROLE,
        subject_ref="workspace_member",
        action_pattern="tool:*",
        effect=PolicyEffect.DENY,
        workspace_id=a,
    )
    await repo.add(rule)
    actor = ActorContext(
        tenant_id=TID,
        workspace_id=b,
        principal_id=USER,
        roles=frozenset({"workspace_member"}),
    )
    rec = await ev.evaluate(
        actor=actor, action="tool:execute:reverse", resource={"workspace_id": str(b)}
    )
    assert rec.effect is PolicyEffect.ALLOW  # rule scoped to A, ignored on B
