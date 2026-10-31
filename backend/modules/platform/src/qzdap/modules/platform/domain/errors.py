"""Platform domain errors."""

from __future__ import annotations

from qzdap_kernel.error_codes import ErrorCode
from qzdap_kernel.errors import AppError, ConflictError, NotFoundError


class PlatformError(AppError):
    """Base for all platform errors."""


class PlanNotFound(PlatformError, NotFoundError):
    code = ErrorCode.PLAN_NOT_FOUND.value


class PlanAlreadyExists(PlatformError, ConflictError):
    code = ErrorCode.PLAN_ALREADY_EXISTS.value


class SubscriptionInvalidTransition(PlatformError, ConflictError):
    code = ErrorCode.SUBSCRIPTION_INVALID_TRANSITION.value


class TenantSettingNotFound(PlatformError, NotFoundError):
    code = ErrorCode.TENANT_SETTING_NOT_FOUND.value


class TenantSettingConflict(PlatformError, ConflictError):
    code = ErrorCode.TENANT_SETTING_CONFLICT.value


__all__ = [
    "PlanAlreadyExists",
    "PlanNotFound",
    "PlatformError",
    "SubscriptionInvalidTransition",
    "TenantSettingConflict",
    "TenantSettingNotFound",
]
