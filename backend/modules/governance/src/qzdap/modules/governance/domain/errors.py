"""Governance domain errors — PolicyError hierarchy."""

from __future__ import annotations

from qzdap_kernel.errors import (
    AppError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationError,
)


class PolicyError(AppError):
    """Base for all governance domain errors.

    Subclasses pick the most appropriate kernel category so HTTP status
    codes map correctly:
    - NotFoundError → 404
    - ConflictError → 409
    - ForbiddenError → 403
    - ValidationError → 422
    """


class PolicyNotFound(PolicyError, NotFoundError):
    code = "POLICY_NOT_FOUND"
    status = 404


class PolicyAlreadyExists(PolicyError, ConflictError):
    code = "POLICY_ALREADY_EXISTS"
    status = 409


class ApprovalNotFound(PolicyError, NotFoundError):
    code = "APPROVAL_NOT_FOUND"
    status = 404


class ApprovalAlreadyDecided(PolicyError, ConflictError):
    code = "APPROVAL_ALREADY_DECIDED"
    status = 409


class ApproverMustDiffer(PolicyError, ForbiddenError):
    code = "APPROVER_MUST_DIFFER"
    status = 403


class InvalidPolicy(PolicyError, ValidationError):
    code = "INVALID_POLICY"
    status = 422


class InvalidApproval(PolicyError, ValidationError):
    code = "INVALID_APPROVAL"
    status = 422


class ApprovalExpired(PolicyError, ConflictError):
    code = "APPROVAL_EXPIRED"
    status = 409


__all__ = [
    "ApprovalAlreadyDecided",
    "ApprovalExpired",
    "ApprovalNotFound",
    "ApproverMustDiffer",
    "InvalidApproval",
    "InvalidPolicy",
    "PolicyAlreadyExists",
    "PolicyError",
    "PolicyNotFound",
]
