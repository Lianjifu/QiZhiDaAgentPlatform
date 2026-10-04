"""Governance domain — value objects + entities + errors + match + events."""

from __future__ import annotations

from qzdap.modules.governance.domain.entities import (
    Approval,
    AuditLogEntry,
    DecisionEvent,
    DecisionRecord,
    PolicyRule,
)
from qzdap.modules.governance.domain.events import (
    ApprovalDecided,
    ApprovalRequested,
    AuditLogAppended,
    DecisionRecorded,
    PolicyCreated,
    PolicyDeleted,
    PolicyUpdated,
)
from qzdap.modules.governance.domain.policy_match import action_precedence, match
from qzdap.modules.governance.domain.value_objects import (
    ApprovalStatus,
    PolicyEffect,
    PolicySubject,
)

__all__ = [
    "Approval",
    "ApprovalDecided",
    "ApprovalRequested",
    "ApprovalStatus",
    "AuditLogAppended",
    "AuditLogEntry",
    "DecisionEvent",
    "DecisionRecord",
    "DecisionRecorded",
    "PolicyCreated",
    "PolicyDeleted",
    "PolicyEffect",
    "PolicyRule",
    "PolicySubject",
    "PolicyUpdated",
    "action_precedence",
    "match",
]
