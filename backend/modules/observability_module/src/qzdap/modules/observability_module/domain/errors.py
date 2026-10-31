"""Observability domain errors.

All descend from :class:`ObservabilityError` (:class:`AppError`).
"""

from __future__ import annotations

from qzdap_kernel.error_codes import ErrorCode
from qzdap_kernel.errors import AppError, ForbiddenError, NotFoundError


class ObservabilityError(AppError):
    """Base for all observability errors."""


class RunRecordNotFound(ObservabilityError, NotFoundError):
    code = ErrorCode.RUN_RECORD_NOT_FOUND.value


class CostRecordNotFound(ObservabilityError, NotFoundError):
    code = ErrorCode.COST_RECORD_NOT_FOUND.value


class QualityScoreNotFound(ObservabilityError, NotFoundError):
    code = ErrorCode.QUALITY_NOT_FOUND.value


class ObservabilityPolicyDenied(ObservabilityError, ForbiddenError):
    code = ErrorCode.OBSERVABILITY_POLICY_DENIED.value
    status = 403


__all__ = [
    "CostRecordNotFound",
    "ObservabilityError",
    "ObservabilityPolicyDenied",
    "QualityScoreNotFound",
    "RunRecordNotFound",
]
