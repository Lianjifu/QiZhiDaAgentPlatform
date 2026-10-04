"""Self-evolution value objects — status / kind enums."""

from __future__ import annotations

from enum import StrEnum


class EvolveStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    APPLIED = "applied"


_TERMINAL_STATUSES = frozenset({EvolveStatus.REJECTED, EvolveStatus.APPLIED})


class EvolveKind(StrEnum):
    MEMORY_PROMOTE = "memory_promote"
    SKILL_PATCH = "skill_patch"
    ROUTING_HINT = "routing_hint"
    DREAM = "dream"


def is_terminal(status: EvolveStatus) -> bool:
    return status in _TERMINAL_STATUSES


__all__ = ["EvolveKind", "EvolveStatus", "is_terminal"]
