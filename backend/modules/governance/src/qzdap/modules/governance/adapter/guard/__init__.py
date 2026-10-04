"""Governance guard adapter."""

from __future__ import annotations

from qzdap.modules.governance.adapter.guard.decorator import policy_check
from qzdap.modules.governance.adapter.guard.policy_guard import PolicyGuard

__all__ = ["PolicyGuard", "policy_check"]
