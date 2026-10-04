"""Agent factory domain errors.

All descend from :class:`AgentFactoryError` (:class:`AppError`) so they
map cleanly through ``qzdap_http.error_envelope`` to RFC-9457 problem
responses.  The eval gate uses :class:`EvalGateFailed` (BusinessRuleError)
raised by ``ReleaseAgentVersionUseCase``; that error lives in
``qzdap_kernel.errors`` and is re-exported here for caller convenience.
"""

from __future__ import annotations

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
    code = "AGENT_TEMPLATE_NOT_FOUND"


class AgentVersionNotFound(AgentFactoryError, NotFoundError):
    code = "AGENT_VERSION_NOT_FOUND"


class ReleaseNotFound(AgentFactoryError, NotFoundError):
    code = "RELEASE_NOT_FOUND"


class AgentTemplateNameConflict(AgentFactoryError, ConflictError):
    code = "AGENT_TEMPLATE_NAME_CONFLICT"
    status = 409


class AgentVersionTagConflict(AgentFactoryError, ConflictError):
    code = "AGENT_VERSION_TAG_CONFLICT"
    status = 409


class AgentVersionImmutable(AgentFactoryError):
    """Raised when a caller attempts to mutate a non-draft version."""

    code = "AGENT_VERSION_IMMUTABLE"
    status = 422


class AgentVersionInvalidTransition(AgentFactoryError):
    """Raised on a disallowed status transition (e.g. released → draft)."""

    code = "AGENT_VERSION_INVALID_TRANSITION"
    status = 422


class AgentFactoryPolicyDenied(AgentFactoryError, ForbiddenError):
    code = "AGENT_FACTORY_POLICY_DENIED"
    status = 403


# Re-export for callers — keeps them out of ``qzdap_kernel`` direct deps.
EvalGateFailed = (
    BusinessRuleError  # signature: (message, *, code="EVAL_GATE_FAILED", status=422)
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
