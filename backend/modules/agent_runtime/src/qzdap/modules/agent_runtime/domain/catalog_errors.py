from __future__ import annotations

from qzdap_kernel.errors import AppError, NotFoundError


class CatalogAgentNotFound(NotFoundError):
    code = "AGENT_NOT_FOUND"


class CatalogAgentDisabled(AppError):
    code = "AGENT_DISABLED"
    status = 409


class CatalogCapabilityUnavailable(AppError):
    code = "AGENT_CAPABILITY_UNAVAILABLE"
    status = 501


__all__ = ["CatalogAgentDisabled", "CatalogAgentNotFound", "CatalogCapabilityUnavailable"]
