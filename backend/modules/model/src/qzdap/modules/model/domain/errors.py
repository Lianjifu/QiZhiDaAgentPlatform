"""Model catalog errors."""

from __future__ import annotations

from qzdap_kernel.errors import AppError, NotFoundError


class ModelError(AppError):
    """Base for model catalog errors."""


class ModelNotFound(ModelError, NotFoundError):
    code = "MODEL_NOT_FOUND"


class ProviderNotFound(ModelError, NotFoundError):
    code = "PROVIDER_NOT_FOUND"


class RouteNotFound(ModelError, NotFoundError):
    code = "ROUTE_NOT_FOUND"


class ModelDisabled(ModelError):
    code = "MODEL_DISABLED"
    status = 403


class CredentialNotFound(ModelError, NotFoundError):
    code = "CREDENTIAL_NOT_FOUND"


class ModelRouteExhausted(ModelError):
    """Phase 3: 路由里所有 model (primary + fallback) 都失败."""

    code = "MODEL_ROUTE_EXHAUSTED"
    status = 502


__all__ = [
    "CredentialNotFound",
    "ModelDisabled",
    "ModelError",
    "ModelNotFound",
    "ModelRouteExhausted",
    "ProviderNotFound",
    "RouteNotFound",
]
