"""Platform value objects — StrEnums."""

from __future__ import annotations

from enum import StrEnum


class SubscriptionStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    CANCELLED = "cancelled"


class PlanStatus(StrEnum):
    ACTIVE = "active"
    HIDDEN = "hidden"
    RETIRED = "retired"


__all__ = ["PlanStatus", "SubscriptionStatus"]
