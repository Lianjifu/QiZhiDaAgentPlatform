"""Workflow catalog errors."""

from __future__ import annotations

from qzdap_kernel.error_codes import ErrorCode
from qzdap_kernel.errors import AppError, NotFoundError


class WorkflowError(AppError):
    """Base for workflow catalog errors."""


class WorkflowNotFound(WorkflowError, NotFoundError):
    code = ErrorCode.WORKFLOW_NOT_FOUND.value


class WorkflowUnavailable(WorkflowError):
    code = ErrorCode.WORKFLOW_UNAVAILABLE.value
    status = 400


__all__ = ["WorkflowError", "WorkflowNotFound", "WorkflowUnavailable"]
