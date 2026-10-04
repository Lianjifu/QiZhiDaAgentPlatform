"""Domain errors for the evaluation module."""

from __future__ import annotations

from qzdap_kernel.errors import (
    AppError,
    BusinessRuleError,
    ConflictError,
    NotFoundError,
)


class EvaluationError(AppError):
    """Base for evaluation module errors."""


class EvalDatasetNotFound(NotFoundError, EvaluationError):
    """Raised when an EvalDataset lookup fails."""


class EvalDatasetNameConflict(ConflictError, EvaluationError):
    """Raised when two datasets in the same tenant share a name."""


class EvalCaseNotFound(NotFoundError, EvaluationError):
    """Raised when an EvalCase lookup fails."""


class EvalRunNotFound(NotFoundError, EvaluationError):
    """Raised when an EvalRun lookup fails."""


class IdempotencyKeyConflict(ConflictError, EvaluationError):
    """Raised when a duplicate (tenant, idempotency_key) eval run POST arrives."""


class EvalGateFailed(BusinessRuleError, EvaluationError):
    """Cross-module signal: the eval gate refused the caller's request."""


__all__ = [
    "EvalCaseNotFound",
    "EvalDatasetNameConflict",
    "EvalDatasetNotFound",
    "EvalGateFailed",
    "EvalRunNotFound",
    "EvaluationError",
    "IdempotencyKeyConflict",
]
