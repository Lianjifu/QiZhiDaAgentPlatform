"""get_plan — fetch a :class:`Plan` by id or code."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from qzdap.modules.platform.domain.entities import Plan
from qzdap.modules.platform.domain.errors import PlanNotFound

if TYPE_CHECKING:
    from qzdap.modules.platform.application.services import PlatformService


def build(service: PlatformService) -> Any:
    async def execute(*, plan_id: str | None = None, code: str | None = None) -> Plan:
        if code:
            plan = await service.plan_repo.get_by_code(code=code)
            if plan is not None:
                return plan
        if plan_id:
            from qzdap_schema.ids import PlanId

            plan = await service.plan_repo.get(plan_id=PlanId(UUID(plan_id)))
            if plan is not None:
                return plan
        raise PlanNotFound("plan not found by id or code")

    return execute


__all__ = ["build"]
