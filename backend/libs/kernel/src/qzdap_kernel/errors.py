"""AppError hierarchy.

All domain code raises `AppError` (or subclasses); the HTTP layer translates
to an RFC-9457-style error envelope. Subclass for semantic categories; do
NOT subclass for new HTTP statuses.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class ErrorEnvelope:
    """Wire-level shape returned to clients on every error.

    Mirrors RFC 9457 Problem Details with our domain extensions.
    """

    code: str  # stable machine code, e.g. "TENANT_DENIED"
    message: str  # human message
    status: int  # HTTP status (mirror of error category)
    details: dict[str, Any]
    trace_id: str | None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "type": f"https://docs.qzdap/errors#{self.code}",
            "title": self.code,
            "status": self.status,
            "code": self.code,
            "message": self.message,
        }
        if self.details:
            out["details"] = self.details
        if self.trace_id:
            out["trace_id"] = self.trace_id
        return out


class AppError(Exception):
    """Base class for every domain exception.

    Subclasses set a default status. Callers may override.
    """

    code: str = "INTERNAL_ERROR"
    status: int = 500

    def __init__(
        self,
        message: str = "",
        *,
        code: str | None = None,
        status: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message or self.code)
        self.message = message or self.code
        if code is not None:
            self.code = code
        if status is not None:
            self.status = status
        self.details: dict[str, Any] = dict(details or {})

    def to_envelope(self, trace_id: str | None = None) -> ErrorEnvelope:
        return ErrorEnvelope(
            code=self.code,
            message=self.message,
            status=self.status,
            details=self.details,
            trace_id=trace_id,
        )


class ValidationError(AppError):
    code = "VALIDATION_ERROR"
    status = 400


class AuthenticationError(AppError):
    code = "AUTHENTICATION_FAILED"
    status = 401


class ForbiddenError(AppError):
    """Raised when the principal lacks permission, or tenant/workspace
    scope does not match. Subclasses are typically not needed; supply
    a code via the constructor.
    """

    code = "FORBIDDEN"
    status = 403


class ActionDeniedError(ForbiddenError):
    """P5 governance: a policy rule with effect=DENY matched.

    Surfaces a 403 with code ``ACTION_DENIED`` so HTTP clients can
    distinguish "you do not have the role" (FORBIDDEN) from "the action
    was explicitly disallowed by a policy" (ACTION_DENIED). The reason
    is the policy's human-readable explanation.
    """

    code = "ACTION_DENIED"
    status = 403

    def __init__(self, reason: str = "", **kwargs: Any) -> None:
        super().__init__(reason or "action denied by policy", **kwargs)
        self.reason = self.message


class ApprovalRequiredError(AppError):
    """P5 governance: a policy rule with effect=REQUIRE_APPROVAL matched.

    Surfaces 202 with code ``APPROVAL_REQUIRED`` and an ``approval_id``
    detail so the HTTP layer can attach ``Location: /v1/approvals/{id}``.
    The business caller retries with ``X-Approval-Id`` once the approval
    has been granted.
    """

    code = "APPROVAL_REQUIRED"
    status = 202

    def __init__(self, approval_id: str = "", **kwargs: Any) -> None:
        super().__init__("approval required", **kwargs)
        self.approval_id = approval_id
        if approval_id:
            self.details["approval_id"] = approval_id


class NotFoundError(AppError):
    code = "NOT_FOUND"
    status = 404


class ConflictError(AppError):
    code = "CONFLICT"
    status = 409


class BusinessRuleError(AppError):
    """Domain invariant violated, or a workflow gate rejected (e.g.
    EVAL_GATE_FAILED, TENANT_DENIED when forbidden, SANDBOX_TIMEOUT, etc.).
    """

    code = "BUSINESS_RULE_VIOLATED"
    status = 422


class RateLimitError(AppError):
    code = "RATE_LIMITED"
    status = 429


class ExternalServiceError(AppError):
    """Upstream system failed (LLM, sandbox, third-party API)."""

    code = "EXTERNAL_SERVICE_ERROR"
    status = 502


class InternalError(AppError):
    """Catch-all for unexpected errors. Always include a stable code so
    operators can find the originating site via logs.
    """

    code = "INTERNAL_ERROR"
    status = 500
