"""list_plans — paginated retrieval of all :class:`Plan` rows.

Plans are global catalog (no tenant filter); ``status`` optionally
narrows to ``active`` / ``hidden`` / ``retired``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from qzdap.modules.platform.domain.entities import Plan

if TYPE_CHECKING:
    from qzdap.modules.platform.application.services import PlatformService


def build(service: PlatformService) -> Any:
    async def execute(
        *, status: str | None = None, limit: int = 100, offset: int = 0
    ) -> list[Plan]:
        return await service.plan_repo.list(status=status, limit=limit, offset=offset)

    return execute


__all__ = ["build"]
