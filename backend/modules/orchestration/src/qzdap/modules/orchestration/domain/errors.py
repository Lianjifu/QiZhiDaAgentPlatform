"""Workflow catalog errors."""

from __future__ import annotations

from qzdap_kernel.errors import AppError, NotFoundError


class WorkflowError(AppError):
    """Base for workflow catalog errors."""


class WorkflowNotFound(WorkflowError, NotFoundError):
    code = "WORKFLOW_NOT_FOUND"


class WorkflowUnavailable(WorkflowError):
    code = "WORKFLOW_UNAVAILABLE"
    status = 400


__all__ = ["WorkflowError", "WorkflowNotFound", "WorkflowUnavailable"]
