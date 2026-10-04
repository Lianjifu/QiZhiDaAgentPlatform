"""Platform domain errors."""

from __future__ import annotations

from qzdap_kernel.errors import AppError, ConflictError, NotFoundError


class PlatformError(AppError):
    """Base for all platform errors."""


class PlanNotFound(PlatformError, NotFoundError):
    code = "PLAN_NOT_FOUND"


class PlanAlreadyExists(PlatformError, ConflictError):
    code = "PLAN_ALREADY_EXISTS"


class SubscriptionInvalidTransition(PlatformError, ConflictError):
    code = "SUBSCRIPTION_INVALID_TRANSITION"


class TenantSettingNotFound(PlatformError, NotFoundError):
    code = "TENANT_SETTING_NOT_FOUND"


class TenantSettingConflict(PlatformError, ConflictError):
    code = "TENANT_SETTING_CONFLICT"


__all__ = [
    "PlanAlreadyExists",
    "PlanNotFound",
    "PlatformError",
    "SubscriptionInvalidTransition",
    "TenantSettingConflict",
    "TenantSettingNotFound",
]
