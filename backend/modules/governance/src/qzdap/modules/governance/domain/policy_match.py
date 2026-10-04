"""Pure policy match function — no I/O, no clock.

The evaluator's hot path does:
  1. fetch candidate rules
  2. for each: ``match(actor, rule, action, resource)`` → bool
  3. sort matched rules by effect precedence + priority
  4. pick the first

This module isolates the predicate so it can be unit-tested exhaustively
without touching the database or the clock.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from qzdap_vault.actor import ActorContext

from qzdap.modules.governance.domain.entities import PolicyRule
from qzdap.modules.governance.domain.value_objects import PolicySubject


@dataclass(slots=True, frozen=True)
class MatchTrace:
    matched: bool
    reason: str = ""


def _glob_match(pattern: str, value: str) -> bool:
    """Glob match: ``*`` matches any (incl. ``:``), ``?`` one char.

    Splits on ``*`` to support multi-segment wildcards. Bare ``*`` was
    rejected at ``PolicyRule.create`` time.
    """
    if not pattern:
        return False
    if "*" not in pattern and "?" not in pattern:
        return pattern == value
    # ``?`` only (no ``*``): every char must match, ``?`` = any one char.
    if "?" in pattern and "*" not in pattern:
        if len(pattern) != len(value):
            return False
        for pc, vc in zip(pattern, value, strict=False):
            if pc == "?" or pc == vc:
                continue
            return False
        return True
    # ``*`` (possibly mixed): split around ``*`` and anchor prefix/middle/suffix.
    tokens = pattern.split("*")
    if not value.startswith(tokens[0]):
        return False
    pos = len(tokens[0])
    for tok in tokens[1:-1]:
        idx = value.find(tok, pos)
        if idx < 0:
            return False
        pos = idx + len(tok)
    if tokens[-1] and not value.endswith(tokens[-1]):
        return False
    if tokens[-1]:
        # remaining middle length must accommodate suffix; prefix+middle
        # already consumed value[:pos], so value must have tokens[-1] suffix.
        pass
    return True


def _subject_matches(actor: ActorContext, rule: PolicyRule) -> bool:
    kind = rule.subject_type
    ref = rule.subject_ref
    if kind is PolicySubject.ROLE:
        return ref in actor.roles
    if kind is PolicySubject.USER:
        return actor.principal_id is not None and str(actor.principal_id) == ref
    if kind is PolicySubject.AGENT:
        # ``ActorContext`` does not carry an agent_id today; agent-scoped
        # rules are reserved for a future iteration where the auth layer
        # exposes the calling agent identity.  For now, always reject so
        # an unmatched rule cannot grant accidental access.
        return False
    return False


def _resource_matches(rule: PolicyRule, resource: dict[str, Any]) -> bool:
    if rule.workspace_id is None:
        return True
    rw = resource.get("workspace_id")
    if rw is None:
        return True  # caller didn't pin — applies tenant-wide rule to any workspace
    return str(rule.workspace_id) == str(rw)


def match(
    actor: ActorContext,
    rule: PolicyRule,
    action: str,
    resource: dict[str, Any],
) -> bool:
    """Return True iff the rule applies to ``actor``/``action``/``resource``."""
    if rule.tenant_id != actor.tenant_id:
        return False
    if not rule.enabled:
        return False
    if not _glob_match(rule.action_pattern, action):
        return False
    if not _subject_matches(actor, rule):
        return False
    return _resource_matches(rule, resource)


def action_precedence(effect: str) -> int:
    """Lower wins. ``deny`` (0) > ``approval`` (1) > ``allow`` (2)."""
    if effect == "deny":
        return 0
    if effect == "approval":
        return 1
    return 2


__all__ = ["MatchTrace", "action_precedence", "match"]
