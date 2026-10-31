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

from fastapi import Request

from qzdap.modules.governance.application.approval_service import ApprovalService
from qzdap.modules.governance.application.data_subject import DataSubjectService
from qzdap.modules.governance.application.policy_evaluator import PolicyEvaluator
from qzdap.modules.governance.application.policy_service import PolicyService


def make_policy_service() -> PolicyService:
    """Real dependency — overridden by composition root via Depends overrides."""
    raise RuntimeError("PolicyService dependency not wired; composition root must override")


def make_approval_service() -> ApprovalService:
    raise RuntimeError("ApprovalService dependency not wired; composition root must override")


def make_policy_evaluator() -> PolicyEvaluator:
    raise RuntimeError("PolicyEvaluator dependency not wired; composition root must override")


async def make_data_subject_service(request: Request) -> DataSubjectService:
    """Real dependency — overridden by composition root via Depends overrides.

    ⚠️ **请求级** ✓ —— 各域的 scope 要**开着自己的会话** ✓（删数据要在一个
    事务里 ✓）→ 不能是「进程级单例」 ✗✗。
    """
    raise RuntimeError("DataSubjectService dependency not wired; composition root must override")


__all__ = [
    "make_approval_service",
    "make_data_subject_service",
    "make_policy_evaluator",
    "make_policy_service",
]
