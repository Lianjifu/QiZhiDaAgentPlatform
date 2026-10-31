"""Use case: delete a tool."""

from __future__ import annotations

from qzdap.modules.tool.application.ports import EventPublisher, ToolRepository
from qzdap.modules.tool.domain import ToolNotFound
from qzdap_kernel.contextvars import current_trace_id
from qzdap_kernel.ids import TenantId, ToolId


class DeleteToolUseCase:
    def __init__(self, tools: ToolRepository, events: EventPublisher) -> None:
        self._tools = tools
        self._events = events

    async def execute(self, *, tenant_id: TenantId, tool_id: ToolId) -> None:
        tool = await self._tools.get(tool_id)
        if tool is None or tool.tenant_id != tenant_id:
            raise ToolNotFound(f"tool {tool_id} not found")
        await self._tools.delete(tool_id)
        await self._events.publish(
            tool.raise_deleted_event(),
            tenant_id=tenant_id,
            workspace_id=tool.workspace_id,
            trace_id=current_trace_id(),
        )
