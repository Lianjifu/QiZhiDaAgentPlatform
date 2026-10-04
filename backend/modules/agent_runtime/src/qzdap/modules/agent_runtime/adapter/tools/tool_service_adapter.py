"""Adapter that exposes `ToolService.invoke_tool()` as a `ToolPort`.

`ToolPort` is the agent-runtime's view of "run a tool by name" — it
doesn't care about tenant scoping, workspace resolution, or call
persistence. The composition root wires a real `ToolService` instance
into the `AgentRuntimeService` so LLM-streamed tool_call chunks can be
executed and produce `ToolResultChunk` SSE messages.
"""

from __future__ import annotations

from uuid import UUID

from qzdap.modules.tool.application.services import ToolService

from qzdap.modules.agent_runtime.application.ports import ToolPort


class ToolServiceAdapter(ToolPort):
    def __init__(
        self,
        *,
        tool_service: ToolService,
        tenant_id: UUID,
        workspace_id: UUID,
        owner_id: UUID,
    ) -> None:
        self._svc = tool_service
        self._tenant_id = tenant_id
        self._workspace_id = workspace_id
        self._owner_id = owner_id

    async def invoke(self, *, call_id: UUID, tool_name: str, arguments: dict) -> dict:
        call = await self._svc.invoke_tool().execute(
            tenant_id=self._tenant_id,
            workspace_id=self._workspace_id,
            owner_id=self._owner_id,
            tool_name=tool_name,
            arguments=arguments,
            call_id=call_id,
        )
        # The invoke_tool use case mutates the ToolCall id from the passed
        # call_id; if the caller didn't supply one (LLM-driven streams may
        # omit it), the use case generates a fresh UUID and persists under
        # that. Either way, the dict result is what callers see.
        return call.result or {}


__all__ = ["ToolServiceAdapter"]
