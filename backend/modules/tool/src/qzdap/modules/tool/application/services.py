"""Top-level tool service — wires the use cases + ports for the
composition root.

The composition root instantiates this with concrete adapters; routes
instantiate use cases via `svc.register_tool()` etc.

A `ToolServiceFactory` (defined in `tool_factory.py` to avoid the
`services ↔ use_cases` circular import) is a per-call session opener
used by the batch use case to run each invocation on its own DB
session — SQLAlchemy async does not permit concurrent operations on a
shared session; see doc 12 §P2 P2.1 follow-up.
"""

from __future__ import annotations

from dataclasses import dataclass

from qzdap.modules.tool.application.ports import (
    CustomInvokerPort,
    EventPublisher,
    MCPRuntime,
    OpenAPIRuntime,
    ToolCallRepository,
    ToolRepository,
)
from qzdap.modules.tool.application.tool_factory import ToolServiceFactory
from qzdap.modules.tool.application.use_cases import (
    BatchInvokeToolsUseCase,
    DeleteToolUseCase,
    GetToolUseCase,
    InvokeToolUseCase,
    ListToolsUseCase,
    RegisterToolUseCase,
    UpdateToolUseCase,
)


@dataclass(slots=True)
class ToolService:
    tools: ToolRepository
    calls: ToolCallRepository
    custom: CustomInvokerPort
    openapi: OpenAPIRuntime
    mcp: MCPRuntime
    events: EventPublisher
    tool_call_timeout_seconds: float = 30.0

    def register_tool(self) -> RegisterToolUseCase:
        return RegisterToolUseCase(self.tools, self.events)

    def list_tools(self) -> ListToolsUseCase:
        return ListToolsUseCase(self.tools)

    def get_tool(self) -> GetToolUseCase:
        return GetToolUseCase(self.tools)

    def update_tool(self) -> UpdateToolUseCase:
        return UpdateToolUseCase(self.tools, self.events)

    def delete_tool(self) -> DeleteToolUseCase:
        return DeleteToolUseCase(self.tools, self.events)

    def invoke_tool(self) -> InvokeToolUseCase:
        return InvokeToolUseCase(
            tools=self.tools,
            calls=self.calls,
            custom=self.custom,
            openapi=self.openapi,
            mcp=self.mcp,
            events=self.events,
            timeout_seconds=self.tool_call_timeout_seconds,
        )

    def batch_invoke_tools(
        self, service_factory: ToolServiceFactory
    ) -> BatchInvokeToolsUseCase:
        """Build a batch use case that opens a fresh service per item.

        The caller supplies a `ToolServiceFactory` (typically the
        composition-root closure over `session_factory + _ToolFactory`).
        """
        return BatchInvokeToolsUseCase(service_factory)
