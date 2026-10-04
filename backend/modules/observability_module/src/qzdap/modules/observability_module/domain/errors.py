"""Observability domain errors.

All descend from :class:`ObservabilityError` (:class:`AppError`).
"""

from __future__ import annotations

from qzdap_kernel.errors import AppError, ForbiddenError, NotFoundError


class ObservabilityError(AppError):
    """Base for all observability errors."""


class RunRecordNotFound(ObservabilityError, NotFoundError):
    code = "RUN_RECORD_NOT_FOUND"


class CostRecordNotFound(ObservabilityError, NotFoundError):
    code = "COST_RECORD_NOT_FOUND"


class QualityScoreNotFound(ObservabilityError, NotFoundError):
    code = "QUALITY_NOT_FOUND"


class ObservabilityPolicyDenied(ObservabilityError, ForbiddenError):
    code = "OBSERVABILITY_POLICY_DENIED"
    status = 403


__all__ = [
    "CostRecordNotFound",
    "ObservabilityError",
    "ObservabilityPolicyDenied",
    "QualityScoreNotFound",
    "RunRecordNotFound",
]
