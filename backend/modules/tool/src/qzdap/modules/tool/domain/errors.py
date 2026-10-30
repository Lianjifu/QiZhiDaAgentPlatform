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


class ToolIdempotencyConflict(ToolError):
    """**同一个幂等键配了不同参数** ✓ —— 调用方的 bug ✓ → 必须暴露 ✓。

    ⚠️ **不静默返回旧结果** ✓ —— 那会让调用方以为「按新参数执行过了」✗✗。
    """

    code = "TOOL_IDEMPOTENCY_CONFLICT"
    status = 409


class ToolExecutionInProgress(ToolError):
    """**同一个幂等键的另一次调用还在跑** ✓ → 不重复执行 ✓。"""

    code = "TOOL_IN_PROGRESS"
    status = 409


class ToolRateLimited(ToolError):
    """**工具被熔断** ✓（连续失败达阈值 ✓ —— 按工具名计 ✓）。

    ⚠️ **带上建议的等待时间** ✓ —— 调用方据此退避 ✓（塞进 ``details`` ✓ ——
    信封里能带出去 ✓）。
    """

    code = "TOOL_RATE_LIMITED"
    status = 429

    def __init__(self, message: str = "", *, retry_after_ms: int = 0, **kwargs) -> None:
        super().__init__(message, **kwargs)
        self.retry_after_ms = retry_after_ms
        self.details["retry_after_ms"] = retry_after_ms


class UpstreamUnavailable(ToolError):
    code = "UPSTREAM_UNAVAILABLE"
    status = 502
