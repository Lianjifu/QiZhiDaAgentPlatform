"""Adapter that exposes `ToolService.invoke_tool()` as a `ToolPort`.

`ToolPort` is the agent-runtime's view of "run a tool by name" — it
doesn't care about tenant scoping, workspace resolution, or call
persistence. The composition root wires a real `ToolService` instance
into the agent runtime so LLM-streamed tool_call chunks can be
executed and produce `ToolResultChunk` SSE messages.
"""

from __future__ import annotations

from uuid import UUID

from qzdap.modules.agent_runtime.application.ports import ToolPort
from qzdap.modules.tool.application.services import ToolService
from qzdap.modules.tool.application.tool_catalog import BUILTIN_TOOL_SPECS
from qzdap.modules.tool.application.tool_schema import (
    tool_description,
    tool_needs_confirm,
    tool_parameters,
    tool_risk,
)


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

    async def invoke(
        self,
        *,
        call_id: UUID,
        tool_name: str,
        arguments: dict,
        turn_id: UUID | None = None,
        idempotency_key: str | None = None,
    ) -> dict:
        call = await self._svc.invoke_tool().execute(
            tenant_id=self._tenant_id,
            workspace_id=self._workspace_id,
            owner_id=self._owner_id,
            tool_name=tool_name,
            arguments=arguments,
            call_id=call_id,
            turn_id=turn_id,
            idempotency_key=idempotency_key,
        )
        # The invoke_tool use case mutates the ToolCall id from the passed
        # call_id; if the caller didn't supply one (LLM-driven streams may
        # omit it), the use case generates a fresh UUID and persists under
        # that. Either way, the dict result is what callers see.
        return call.result or {}

    async def list_tools(self) -> list[dict]:
        """Enumerate the tenant's enabled tools with their argument contract.

        The ``tools`` rows carry name + description but an empty ``spec``
        for the built-ins, so the function schema the model sees comes
        from the static built-in catalog. Admin registered OpenAPI / MCP
        tools carry their real spec — their schema is derived from it
        (an empty ``properties`` object would leave the model guessing).
        """
        try:
            rows = await self._svc.list_tools().execute(
                tenant_id=self._tenant_id,
                enabled=True,
                limit=200,
            )
        except Exception:
            return []

        out: list[dict] = []
        for row in rows:
            name = str(row.name)
            spec = BUILTIN_TOOL_SPECS.get(name)
            if spec is not None:
                out.append(
                    {
                        "name": name,
                        "description": spec["description"],
                        "parameters": spec["parameters"],
                        "risk": spec.get("risk", "low"),
                        "needConfirm": bool(spec.get("needConfirm", False)),
                    }
                )
                continue
            out.append(
                {
                    "name": name,
                    "description": tool_description(row),
                    "parameters": tool_parameters(row),
                    "risk": tool_risk(row),
                    "needConfirm": tool_needs_confirm(row),
                    "protocol": str(getattr(row.protocol, "value", row.protocol)),
                }
            )
        return out


__all__ = ["ToolServiceAdapter"]
