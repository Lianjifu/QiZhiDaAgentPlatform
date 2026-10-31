"""Agent factory domain errors.

All descend from :class:`AgentFactoryError` (:class:`AppError`) so they
map cleanly through ``qzdap_http.error_envelope`` to RFC-9457 problem
responses.  The eval gate uses :class:`EvalGateFailed` (BusinessRuleError)
raised by ``ReleaseAgentVersionUseCase``; that error lives in
``qzdap_kernel.errors`` and is re-exported here for caller convenience.
"""

from __future__ import annotations

from qzdap_kernel.error_codes import ErrorCode
from qzdap_kernel.errors import (
    AppError,
    BusinessRuleError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
)


class AgentFactoryError(AppError):
    """Base for all agent_factory errors."""


class AgentTemplateNotFound(AgentFactoryError, NotFoundError):
    code = ErrorCode.AGENT_TEMPLATE_NOT_FOUND.value


class AgentVersionNotFound(AgentFactoryError, NotFoundError):
    code = ErrorCode.AGENT_VERSION_NOT_FOUND.value


class ReleaseNotFound(AgentFactoryError, NotFoundError):
    code = ErrorCode.RELEASE_NOT_FOUND.value


class AgentTemplateNameConflict(AgentFactoryError, ConflictError):
    code = ErrorCode.AGENT_TEMPLATE_NAME_CONFLICT.value
    status = 409


class AgentVersionTagConflict(AgentFactoryError, ConflictError):
    code = ErrorCode.AGENT_VERSION_TAG_CONFLICT.value
    status = 409


class AgentVersionImmutable(AgentFactoryError):
    """Raised when a caller attempts to mutate a non-draft version."""

    code = ErrorCode.AGENT_VERSION_IMMUTABLE.value
    status = 422


class AgentVersionInvalidTransition(AgentFactoryError):
    """Raised on a disallowed status transition (e.g. released → draft)."""

    code = ErrorCode.AGENT_VERSION_INVALID_TRANSITION.value
    status = 422


class AgentFactoryPolicyDenied(AgentFactoryError, ForbiddenError):
    code = ErrorCode.AGENT_FACTORY_POLICY_DENIED.value
    status = 403


# Re-export for callers — keeps them out of ``qzdap_kernel`` direct deps.
EvalGateFailed = (
    BusinessRuleError  # signature: (message, *, code=ErrorCode.EVAL_GATE_FAILED.value, status=422)
)


__all__ = [
    "AgentFactoryError",
    "AgentFactoryPolicyDenied",
    "AgentTemplateNameConflict",
    "AgentTemplateNotFound",
    "AgentVersionImmutable",
    "AgentVersionInvalidTransition",
    "AgentVersionNotFound",
    "AgentVersionTagConflict",
    "EvalGateFailed",
    "ReleaseNotFound",
]
