from __future__ import annotations

from qzdap_kernel.error_codes import ErrorCode
from qzdap_kernel.errors import AppError, NotFoundError


class CatalogAgentNotFound(NotFoundError):
    code = ErrorCode.AGENT_NOT_FOUND.value


class CatalogAgentDisabled(AppError):
    code = ErrorCode.AGENT_DISABLED.value
    status = 409


class CatalogCapabilityUnavailable(AppError):
    code = ErrorCode.AGENT_CAPABILITY_UNAVAILABLE.value
    status = 501


__all__ = ["CatalogAgentDisabled", "CatalogAgentNotFound", "CatalogCapabilityUnavailable"]
