"""Identity-module domain errors. Subclasses of kernel AppError."""

from __future__ import annotations

from qzdap_kernel.errors import BusinessRuleError, ConflictError, NotFoundError


class TenantNotFound(NotFoundError):
    code = "TENANT_NOT_FOUND"


class WorkspaceNotFound(NotFoundError):
    code = "WORKSPACE_NOT_FOUND"


class UserNotFound(NotFoundError):
    code = "USER_NOT_FOUND"


class APIKeyNotFound(NotFoundError):
    code = "API_KEY_NOT_FOUND"


class TenantAlreadyExists(ConflictError):
    code = "TENANT_ALREADY_EXISTS"


class WorkspaceAlreadyExists(ConflictError):
    code = "WORKSPACE_ALREADY_EXISTS"


class UserAlreadyExists(ConflictError):
    code = "USER_ALREADY_EXISTS"


class InvalidCredentials(BusinessRuleError):
    code = "INVALID_CREDENTIALS"
    # Override BusinessRuleError's 422 with 401 — auth failures must surface
    # as 401 per RFC 9110 §15.5.2 so HTTP middleware (basic-auth realm,
    # WWW-Authenticate, etc.) handles them correctly.
    status = 401


class APIKeyRevoked(BusinessRuleError):
    code = "API_KEY_REVOKED"


class WorkspaceLimitReached(BusinessRuleError):
    code = "WORKSPACE_LIMIT_REACHED"
