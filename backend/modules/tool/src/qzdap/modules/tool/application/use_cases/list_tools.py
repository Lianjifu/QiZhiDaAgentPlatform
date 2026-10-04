"""Use case: list tools with optional enabled-filter and pagination."""

from __future__ import annotations

from uuid import UUID

from qzdap.modules.tool.application.ports import ToolRepository
from qzdap.modules.tool.domain import Tool


class ListToolsUseCase:
    def __init__(self, tools: ToolRepository) -> None:
        self._tools = tools

    async def execute(
        self,
        *,
        tenant_id: UUID,
        enabled: bool | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Tool]:
        return await self._tools.list(
            tenant_id=tenant_id,
            enabled=enabled,
            limit=limit,
            offset=offset,
        )
