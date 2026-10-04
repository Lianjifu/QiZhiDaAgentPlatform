"""Use case: update a tool with optional optimistic concurrency check."""

from __future__ import annotations

from uuid import UUID

from qzdap_kernel.contextvars import current_trace_id

from qzdap.modules.tool.application.ports import EventPublisher, ToolRepository
from qzdap.modules.tool.domain import (
    AuthConfig,
    SpecOperation,
    Tool,
    ToolNotFound,
    ToolVersionMismatch,
)


class UpdateToolUseCase:
    def __init__(self, tools: ToolRepository, events: EventPublisher) -> None:
        self._tools = tools
        self._events = events

    async def execute(
        self,
        *,
        tenant_id: UUID,
        tool_id: UUID,
        expected_version: int | None,
        description: str | None,
        spec: dict | None,
        auth_config: AuthConfig | None,
        clear_auth: bool,
        rate_limit_per_minute: int | None,
        clear_rate_limit: bool,
        enabled: bool | None,
    ) -> Tool:
        tool = await self._tools.get(tool_id)
        if tool is None or tool.tenant_id != tenant_id:
            raise ToolNotFound(f"tool {tool_id} not found")
        if expected_version is not None and tool.version != expected_version:
            raise ToolVersionMismatch(
                f"tool {tool_id} version mismatch: expected {expected_version}, "
                f"got {tool.version}",
                code="TOOL_VERSION_MISMATCH",
            )

        new_ops: list[SpecOperation] | None = None
        if spec is not None:
            new_ops = Tool.extract_operations(protocol=tool.protocol, spec=spec)

        updated = tool.update(
            description=description,
            spec=spec,
            spec_operations=new_ops,
            auth_config=auth_config,
            clear_auth=clear_auth,
            rate_limit_per_minute=rate_limit_per_minute,
            clear_rate_limit=clear_rate_limit,
            enabled=enabled,
        )
        await self._tools.update(updated)
        await self._events.publish(
            updated.raise_updated_event(),
            tenant_id=tenant_id,
            workspace_id=updated.workspace_id,
            trace_id=current_trace_id(),
        )
        return updated
