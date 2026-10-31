"""Use case: get a tool by ID."""

from __future__ import annotations

from qzdap.modules.tool.application.ports import ToolRepository
from qzdap.modules.tool.domain import Tool, ToolNotFound
from qzdap_kernel.ids import TenantId, ToolId


class GetToolUseCase:
    def __init__(self, tools: ToolRepository) -> None:
        self._tools = tools

    async def execute(self, *, tenant_id: TenantId, tool_id: ToolId) -> Tool:
        tool = await self._tools.get(tool_id)
        if tool is None or tool.tenant_id != tenant_id:
            raise ToolNotFound(f"tool {tool_id} not found")
        return tool
