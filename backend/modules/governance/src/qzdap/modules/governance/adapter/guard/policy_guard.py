"""PolicyGuard — translates a DecisionRecord into a kernel error or pass.

Use:

    await policy_guard.check(actor=actor, action="tool:execute:reverse",
                             resource={"tool": "reverse"})

The guard is intentionally stateless apart from its ``PolicyEvaluator``
dependency — it adds no I/O of its own.  Use cases call it as the first
line of ``execute()``.
"""

from __future__ import annotations

from typing import Any

from qzdap_kernel.errors import ActionDeniedError, ApprovalRequiredError
from qzdap_vault.actor import ActorContext

from qzdap.modules.governance.application.policy_evaluator import PolicyEvaluator
from qzdap.modules.governance.domain.entities import DecisionRecord
from qzdap.modules.governance.domain.value_objects import PolicyEffect as POL_EFFECT


class PolicyGuard:
    def __init__(self, evaluator: PolicyEvaluator) -> None:
        self._evaluator = evaluator

    async def check(
        self,
        *,
        actor: ActorContext,
        action: str,
        resource: dict[str, Any] | None = None,
    ) -> DecisionRecord:
        rec = await self._evaluator.evaluate(
            actor=actor, action=action, resource=resource or {}
        )
        if rec.effect is POL_EFFECT.DENY:
            raise ActionDeniedError(
                reason=rec.reason,
                code="ACTION_DENIED",
                details={
                    "action": action,
                    "rule_id": str(rec.rule_id) if rec.rule_id else None,
                },
            )
        if rec.effect is POL_EFFECT.REQUIRE_APPROVAL:
            raise ApprovalRequiredError(
                approval_id=str(rec.approval_id) if rec.approval_id else "",  # type: ignore[arg-type]
                code="APPROVAL_REQUIRED",
                details={
                    "action": action,
                    "rule_id": str(rec.rule_id) if rec.rule_id else None,
                    "approval_id": str(rec.approval_id) if rec.approval_id else None,
                    "reason": rec.reason,
                },
            )
        return rec


__all__ = ["PolicyGuard"]
