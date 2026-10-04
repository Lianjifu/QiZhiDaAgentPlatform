"""Domain errors for the tool module.

Subclasses of `qzdap_kernel.errors.AppError`. Code/status are stable
wire-level identifiers the HTTP layer passes through to the client.
"""

from __future__ import annotations

from qzdap_kernel.errors import AppError, NotFoundError


class ToolError(AppError):
    """Base class for tool-module domain errors."""


class ToolNotFound(ToolError, NotFoundError):
    code = "TOOL_NOT_FOUND"


class ToolAlreadyExists(ToolError):
    code = "TOOL_ALREADY_EXISTS"
    status = 409


class ToolVersionMismatch(ToolError):
    """Raised when an update's `If-Match` version doesn't match the row."""

    code = "TOOL_VERSION_MISMATCH"
    status = 412


class InvalidToolSpec(ToolError):
    """Raised when the registration spec is malformed or unsupported."""

    code = "INVALID_TOOL_SPEC"
    status = 422


class ToolDisabled(ToolError):
    """Raised when invocation targets a `enabled=False` tool."""

    code = "TOOL_DISABLED"
    status = 409


class ToolCallTimeout(ToolError):
    code = "TOOL_CALL_TIMEOUT"
    status = 504


class UpstreamUnavailable(ToolError):
    code = "UPSTREAM_UNAVAILABLE"
    status = 502
