"""assign_subscription — create or replace a tenant's subscription.

Single subscription per tenant: if one already exists, update its
``plan_id`` / ``plan_code`` / ``updated_by``.  Otherwise insert a new
row.  Idempotent.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from qzdap_kernel.errors import BusinessRuleError
from qzdap_schema.ids import TenantId, UserId

from qzdap.modules.platform.domain.entities import Subscription
from qzdap.modules.platform.domain.errors import PlanNotFound

if TYPE_CHECKING:
    from qzdap.modules.platform.application.services import PlatformService


def build(service: PlatformService) -> Any:
    async def execute(
        *,
        tenant_id: TenantId,
        plan_code: str,
        updated_by: UserId | None = None,
        auto_renew: bool = True,
    ) -> Subscription:
        plan = await service.plan_repo.get_by_code(code=plan_code)
        if plan is None:
            raise PlanNotFound(f"plan with code {plan_code!r} not found")
        if plan.status.value == "retired":
            raise BusinessRuleError(
                message=f"plan {plan_code!r} is retired and cannot be assigned",
                code="PLAN_RETIRED",
            )
        existing = await service.subscription_repo.get_for_tenant(tenant_id=tenant_id)
        now = datetime.now(UTC)
        if existing is None:
            sub = Subscription.assign(
                tenant_id=tenant_id,
                plan_id=plan.id,
                plan_code=plan.code,
                updated_by=updated_by,
                auto_renew=auto_renew,
                now=now,
            )
            return await service.subscription_repo.add(sub)
        # replace plan on existing sub
        from dataclasses import replace

        new_sub = replace(
            existing,
            plan_id=plan.id,
            plan_code=plan.code,
            auto_renew=auto_renew,
            updated_by=updated_by,
            updated_at=now,
            started_at=now,
        )
        return await service.subscription_repo.update(new_sub)

    return execute


__all__ = ["build"]
