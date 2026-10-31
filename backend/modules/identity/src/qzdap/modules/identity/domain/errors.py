"""Identity-module domain errors. Subclasses of kernel AppError."""

from __future__ import annotations

from qzdap_kernel.error_codes import ErrorCode
from qzdap_kernel.errors import BusinessRuleError, ConflictError, NotFoundError


class TenantNotFound(NotFoundError):
    code = ErrorCode.TENANT_NOT_FOUND.value


class WorkspaceNotFound(NotFoundError):
    code = ErrorCode.WORKSPACE_NOT_FOUND.value


class UserNotFound(NotFoundError):
    code = ErrorCode.USER_NOT_FOUND.value


class APIKeyNotFound(NotFoundError):
    code = ErrorCode.API_KEY_NOT_FOUND.value


class TenantAlreadyExists(ConflictError):
    code = ErrorCode.TENANT_ALREADY_EXISTS.value


class WorkspaceAlreadyExists(ConflictError):
    code = ErrorCode.WORKSPACE_ALREADY_EXISTS.value


class UserAlreadyExists(ConflictError):
    code = ErrorCode.USER_ALREADY_EXISTS.value


class InvalidCredentials(BusinessRuleError):
    code = ErrorCode.INVALID_CREDENTIALS.value
    # Override BusinessRuleError's 422 with 401 — auth failures must surface
    # as 401 per RFC 9110 §15.5.2 so HTTP middleware (basic-auth realm,
    # WWW-Authenticate, etc.) handles them correctly.
    status = 401


class APIKeyRevoked(BusinessRuleError):
    code = ErrorCode.API_KEY_REVOKED.value


class WorkspaceLimitReached(BusinessRuleError):
    code = ErrorCode.WORKSPACE_LIMIT_REACHED.value
