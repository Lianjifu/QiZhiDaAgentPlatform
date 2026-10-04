"""Tests for ``domain/policy_match.py`` — the pure predicate.

Covers:
- ``_glob_match``: exact, prefix wildcard, middle wildcard, suffix
  wildcard, ``?`` single-char
- ``_subject_matches``: ROLE hit/miss, USER hit/miss, AGENT always False
- ``_resource_matches``: tenant-wide rule, workspace-scoped rule hit/miss
- ``match()`` end-to-end: tenant boundary, disabled rule, full positive
- ``action_precedence()``: deny < approval < allow
"""

from __future__ import annotations

from uuid import UUID, uuid4

from qzdap_schema.ids import PolicyId, TenantId, WorkspaceId
from qzdap_vault.actor import ActorContext

from qzdap.modules.governance.domain.entities import PolicyRule
from qzdap.modules.governance.domain.policy_match import (
    _glob_match,
    _resource_matches,
    _subject_matches,
    action_precedence,
    match,
)
from qzdap.modules.governance.domain.value_objects import PolicyEffect, PolicySubject

TID = TenantId(UUID("00000000-0000-0000-0000-000000000001"))
WID = WorkspaceId(UUID("00000000-0000-0000-0000-000000000002"))
PID = PolicyId(UUID("00000000-0000-0000-0000-000000000003"))
USER = UUID("00000000-0000-0000-0000-00000000000a")


def _actor(
    *, roles=("workspace_member",), workspace_id=None, principal_id=USER
) -> ActorContext:
    return ActorContext(
        tenant_id=TID,
        workspace_id=workspace_id,
        principal_id=principal_id,
        roles=frozenset(roles),
    )


def _rule(
    *,
    action="tool:execute:reverse",
    effect=PolicyEffect.ALLOW,
    subject_type=PolicySubject.ROLE,
    subject_ref="workspace_member",
    workspace_id=None,
    enabled=True,
) -> PolicyRule:
    return PolicyRule(
        id=PID,
        tenant_id=TID,
        workspace_id=workspace_id,
        subject_type=subject_type,
        subject_ref=subject_ref,
        action_pattern=action,
        effect=effect,
        enabled=enabled,
    )


# ── _glob_match ─────────────────────────────────────────────────────────────


def test_glob_match_exact_string():
    assert _glob_match("tool:execute:reverse", "tool:execute:reverse") is True
    assert _glob_match("tool:execute:reverse", "tool:execute:clock") is False


def test_glob_match_prefix_wildcard():
    assert _glob_match("tool:execute:*", "tool:execute:reverse") is True
    assert _glob_match("tool:execute:*", "tool:execute:") is True
    assert _glob_match("tool:execute:*", "tool:register:clock") is False


def test_glob_match_middle_wildcard():
    assert _glob_match("tool:*:reverse", "tool:execute:reverse") is True
    assert _glob_match("tool:*:reverse", "tool:register:reverse") is True
    assert _glob_match("tool:*:reverse", "tool:execute:clock") is False


def test_glob_match_suffix_wildcard():
    assert _glob_match("*:reverse", "tool:execute:reverse") is True
    assert _glob_match("*:reverse", "skill:invoke:reverse") is True
    assert _glob_match("*:reverse", "tool:execute:clock") is False


def test_glob_match_question_mark():
    assert _glob_match("tool:?x", "tool:ax") is True
    assert _glob_match("tool:?x", "tool:bx") is True
    assert _glob_match("tool:?x", "tool:abx") is False
    assert _glob_match("tool:?x", "tool:x") is False


# ── _subject_matches ────────────────────────────────────────────────────────


def test_subject_match_role_hit():
    actor = _actor(roles={"workspace_member"})
    assert _subject_matches(actor, _rule()) is True


def test_subject_match_role_miss():
    actor = _actor(roles={"other_role"})
    assert _subject_matches(actor, _rule()) is False


def test_subject_match_user_hit_and_miss():
    actor = _actor(principal_id=USER)
    rule = _rule(subject_type=PolicySubject.USER, subject_ref=str(USER))
    assert _subject_matches(actor, rule) is True

    rule = _rule(subject_type=PolicySubject.USER, subject_ref=str(uuid4()))
    assert _subject_matches(actor, rule) is False


def test_subject_match_agent_always_false():
    actor = _actor()
    rule = _rule(subject_type=PolicySubject.AGENT, subject_ref="agent:agt_x")
    assert _subject_matches(actor, rule) is False


# ── _resource_matches ───────────────────────────────────────────────────────


def test_resource_match_tenant_wide_rule():
    rule = _rule(workspace_id=None)
    assert _resource_matches(rule, {"workspace_id": str(WID)}) is True
    assert _resource_matches(rule, {}) is True


def test_resource_match_workspace_scoped_hit():
    rule = _rule(workspace_id=WID)
    assert _resource_matches(rule, {"workspace_id": str(WID)}) is True


def test_resource_match_workspace_scoped_miss():
    rule = _rule(workspace_id=WID)
    other = UUID("00000000-0000-0000-0000-000000000099")
    assert _resource_matches(rule, {"workspace_id": str(other)}) is False


# ── match() end-to-end ─────────────────────────────────────────────────────


def test_match_full_positive():
    actor = _actor(roles={"workspace_member"})
    rule = _rule()
    assert (
        match(actor, rule, "tool:execute:reverse", {"workspace_id": str(WID)}) is True
    )


def test_match_disabled_rule_excluded():
    actor = _actor(roles={"workspace_member"})
    rule = _rule(enabled=False)
    assert match(actor, rule, "tool:execute:reverse", {}) is False


def test_match_tenant_boundary():
    actor = _actor()
    other = ActorContext(
        tenant_id=TenantId(uuid4()),
        workspace_id=None,
        principal_id=USER,
        roles=frozenset({"workspace_member"}),
    )
    rule = _rule()
    assert match(actor, rule, "tool:execute:reverse", {}) is True
    assert match(other, rule, "tool:execute:reverse", {}) is False


# ── action_precedence ──────────────────────────────────────────────────────


def test_action_precedence_ordering():
    assert action_precedence("deny") < action_precedence("approval")
    assert action_precedence("approval") < action_precedence("allow")


def test_action_precedence_unknown_treated_as_allow():
    assert action_precedence("bogus") == 2
