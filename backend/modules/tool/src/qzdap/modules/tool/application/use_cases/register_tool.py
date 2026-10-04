"""Use case: register a new Tool."""

from __future__ import annotations

from uuid import UUID, uuid4

from qzdap_kernel.contextvars import current_trace_id
from qzdap_schema.ids import ToolId

from qzdap.modules.tool.application.ports import EventPublisher, ToolRepository
from qzdap.modules.tool.domain import (
    AuthConfig,
    SpecOperation,
    Tool,
    ToolAlreadyExists,
    ToolProtocol,
)


class RegisterToolUseCase:
    def __init__(self, tools: ToolRepository, events: EventPublisher) -> None:
        self._tools = tools
        self._events = events

    async def execute(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        owner_id: UUID,
        name: str,
        description: str,
        protocol: ToolProtocol,
        spec: dict,
        auth_config: AuthConfig | None,
        rate_limit_per_minute: int | None,
    ) -> Tool:
        existing = await self._tools.get_by_name(tenant_id=tenant_id, name=name)
        if existing is not None:
            raise ToolAlreadyExists(
                f"tool {name!r} already exists in tenant",
                code="TOOL_ALREADY_EXISTS",
            )

        operations: list[SpecOperation] = Tool.extract_operations(
            protocol=protocol, spec=spec
        )

        tool = Tool.create(
            id=ToolId(uuid4()),
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            name=name,
            description=description,
            protocol=protocol,
            spec=spec,
            spec_operations=operations,
            auth_config=auth_config,
            rate_limit_per_minute=rate_limit_per_minute,
        )
        await self._tools.add(tool)
        await self._events.publish(
            tool.raise_registered_event(),
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            trace_id=current_trace_id(),
        )
        return tool
