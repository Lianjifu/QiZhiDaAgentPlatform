from __future__ import annotations

from qzdap_kernel.errors import AppError, NotFoundError


class CatalogAgentNotFound(NotFoundError):
    code = "AGENT_NOT_FOUND"


class CatalogAgentDisabled(AppError):
    code = "AGENT_DISABLED"
    status = 409


__all__ = ["CatalogAgentDisabled", "CatalogAgentNotFound"]
