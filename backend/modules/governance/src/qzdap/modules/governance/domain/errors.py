"""Governance domain errors — PolicyError hierarchy."""

from __future__ import annotations

from qzdap_kernel.error_codes import ErrorCode
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
    code = ErrorCode.POLICY_NOT_FOUND.value
    status = 404


class PolicyAlreadyExists(PolicyError, ConflictError):
    code = ErrorCode.POLICY_ALREADY_EXISTS.value
    status = 409


class ApprovalNotFound(PolicyError, NotFoundError):
    code = ErrorCode.APPROVAL_NOT_FOUND.value
    status = 404


class ApprovalAlreadyDecided(PolicyError, ConflictError):
    code = ErrorCode.APPROVAL_ALREADY_DECIDED.value
    status = 409


class ApproverMustDiffer(PolicyError, ForbiddenError):
    code = ErrorCode.APPROVER_MUST_DIFFER.value
    status = 403


class InvalidPolicy(PolicyError, ValidationError):
    code = ErrorCode.INVALID_POLICY.value
    status = 422


class InvalidApproval(PolicyError, ValidationError):
    code = ErrorCode.INVALID_APPROVAL.value
    status = 422


class ApprovalExpired(PolicyError, ConflictError):
    code = ErrorCode.APPROVAL_EXPIRED.value
    status = 409


class DataSubjectFailed(PolicyError, ValidationError):
    """**数据主体请求没做完** ✓（C9 ✓）—— 某个 scope 失败了 ✓。

    ⚠️ **不是「没找到」** ✓ —— 是「**做了但没做完**」✓ → 422 ✓。
    """

    code = ErrorCode.DATA_SUBJECT_FAILED.value
    status = 422


__all__ = [
    "ApprovalAlreadyDecided",
    "ApprovalExpired",
    "ApprovalNotFound",
    "ApproverMustDiffer",
    "DataSubjectFailed",
    "InvalidApproval",
    "InvalidPolicy",
    "PolicyAlreadyExists",
    "PolicyError",
    "PolicyNotFound",
]
