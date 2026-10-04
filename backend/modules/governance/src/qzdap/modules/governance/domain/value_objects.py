"""Governance value objects — StrEnum + small dataclasses."""

from __future__ import annotations

from enum import StrEnum


class PolicyEffect(StrEnum):
    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_APPROVAL = "approval"


class PolicySubject(StrEnum):
    ROLE = "role"
    USER = "user"
    AGENT = "agent"


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    EXPIRED = "expired"


__all__ = ["ApprovalStatus", "PolicyEffect", "PolicySubject"]
