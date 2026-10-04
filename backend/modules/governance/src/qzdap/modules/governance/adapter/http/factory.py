"""Per-call factory for governance use cases (mirror tool_dependency pattern).

The composition root provides the underlying ``PolicyService`` /
``ApprovalService`` / ``PolicyEvaluator`` via FastAPI's
``app.dependency_overrides`` (or by setting the module-level singletons
on this module).

These helpers are the indirection that lets the composition root swap
the underlying service (test fakes, instrumentation, etc.) without
touching the router.
"""

from __future__ import annotations

from qzdap.modules.governance.application.approval_service import ApprovalService
from qzdap.modules.governance.application.policy_evaluator import PolicyEvaluator
from qzdap.modules.governance.application.policy_service import PolicyService


def make_policy_service() -> PolicyService:
    """Real dependency — overridden by composition root via Depends overrides."""
    raise RuntimeError(
        "PolicyService dependency not wired; composition root must override"
    )


def make_approval_service() -> ApprovalService:
    raise RuntimeError(
        "ApprovalService dependency not wired; composition root must override"
    )


def make_policy_evaluator() -> PolicyEvaluator:
    raise RuntimeError(
        "PolicyEvaluator dependency not wired; composition root must override"
    )


__all__ = [
    "make_approval_service",
    "make_policy_evaluator",
    "make_policy_service",
]
