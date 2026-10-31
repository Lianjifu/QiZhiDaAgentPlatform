"""Model catalog errors."""

from __future__ import annotations

from qzdap_kernel.error_codes import ErrorCode
from qzdap_kernel.errors import AppError, NotFoundError


class ModelError(AppError):
    """Base for model catalog errors."""


class ModelNotFound(ModelError, NotFoundError):
    code = ErrorCode.MODEL_NOT_FOUND.value


class ProviderNotFound(ModelError, NotFoundError):
    code = ErrorCode.PROVIDER_NOT_FOUND.value


class RouteNotFound(ModelError, NotFoundError):
    code = ErrorCode.ROUTE_NOT_FOUND.value


class ModelDisabled(ModelError):
    code = ErrorCode.MODEL_DISABLED.value
    status = 403


class CredentialNotFound(ModelError, NotFoundError):
    code = ErrorCode.CREDENTIAL_NOT_FOUND.value


class ModelRouteExhausted(ModelError):
    """Phase 3: 路由里所有 model (primary + fallback) 都失败."""

    code = ErrorCode.MODEL_ROUTE_EXHAUSTED.value
    status = 502


class QuotaExceeded(ModelError):
    """Phase 4: tenant/model 配额超额."""

    code = ErrorCode.QUOTA_EXCEEDED.value
    status = 429


__all__ = [
    "CredentialNotFound",
    "ModelDisabled",
    "ModelError",
    "ModelNotFound",
    "ModelRouteExhausted",
    "ProviderNotFound",
    "QuotaExceeded",
    "RouteNotFound",
]
