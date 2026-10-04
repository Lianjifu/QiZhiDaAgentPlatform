"""企智搭 · 智能体平台 — kernel package.

Defines the foundational types: Principal, TenantContext, WorkspaceContext,
trace_id context variable, and the AppError hierarchy.
"""

from qzdap_kernel.contexts import TenantContext, TenantWorkspaceContext, WorkspaceContext
from qzdap_kernel.contextvars import current_trace_id, new_trace_id, trace_id_var
from qzdap_kernel.errors import (
    AppError,
    AuthenticationError,
    BusinessRuleError,
    ConflictError,
    ErrorEnvelope,
    ExternalServiceError,
    ForbiddenError,
    InternalError,
    NotFoundError,
    RateLimitError,
    ValidationError,
)
from qzdap_kernel.events import DomainEvent
from qzdap_kernel.principal import Principal, PrincipalType

__all__ = [
    "AppError",
    "AuthenticationError",
    "BusinessRuleError",
    "ConflictError",
    "DomainEvent",
    "ErrorEnvelope",
    "ExternalServiceError",
    "ForbiddenError",
    "InternalError",
    "NotFoundError",
    "Principal",
    "PrincipalType",
    "RateLimitError",
    "TenantContext",
    "TenantWorkspaceContext",
    "ValidationError",
    "WorkspaceContext",
    "current_trace_id",
    "new_trace_id",
    "trace_id_var",
]
