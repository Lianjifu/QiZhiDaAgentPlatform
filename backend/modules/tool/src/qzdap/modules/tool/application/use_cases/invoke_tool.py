"""Use case: invoke a tool by name, dispatching to the right protocol.

Lifecycle:
  1. Look up Tool by (tenant_id, name). 404 if not found.
  2. Reject disabled tools with 409 TOOL_DISABLED.
  3. Persist a ToolCall(status=running). Emit ToolInvoked.
  4. Dispatch by protocol:
       - CUSTOM   → process-local registry
       - OPENAPI  → httpx POST to operation_id, with auth injection
       - MCP      → JSON-RPC over HTTP, tools/call
  5. Persist success/failure row. Emit ToolCompleted / ToolFailed.
  6. Translate httpx errors to domain errors (504 / 502) without leaking
     upstream URLs / headers.
"""

from __future__ import annotations

from time import monotonic
from uuid import UUID, uuid4

import httpx
from qzdap_kernel.contextvars import current_trace_id
from qzdap_schema.ids import ToolCallId

from qzdap.modules.tool.application.ports import (
    CustomInvokerPort,
    EventPublisher,
    MCPRuntime,
    OpenAPIRuntime,
    ToolCallRepository,
    ToolRepository,
)
from qzdap.modules.tool.domain import (
    SpecOperation,
    ToolCall,
    ToolDisabled,
    ToolNotFound,
    ToolProtocol,
)
from qzdap.modules.tool.domain.errors import ToolCallTimeout, UpstreamUnavailable


def _pick_operation(operations: list[SpecOperation], arguments: dict) -> SpecOperation:
    """Pick the single operation referenced by `arguments["__operation_id"]`.

    The HTTP DTO copies the operationId into `arguments` so we can route
    without inventing a separate field on the request body."""
    op_id = arguments.get("__operation_id")
    if not isinstance(op_id, str) or not op_id:
        raise InvalidToolSpecCallError(
            "openapi invocation requires '__operation_id' in arguments"
        )
    for op in operations:
        if op.operation_id == op_id:
            return op
    raise InvalidToolSpecCallError(f"unknown operation_id {op_id!r}")


class InvalidToolSpecCallError(Exception):
    """Local sentinel — translated to 422 by the HTTP layer."""


class InvokeToolUseCase:
    def __init__(
        self,
        *,
        tools: ToolRepository,
        calls: ToolCallRepository,
        custom: CustomInvokerPort,
        openapi: OpenAPIRuntime,
        mcp: MCPRuntime,
        events: EventPublisher,
        timeout_seconds: float = 30.0,
        policy_guard: object | None = None,
    ) -> None:
        self._tools = tools
        self._calls = calls
        self._custom = custom
        self._openapi = openapi
        self._mcp = mcp
        self._events = events
        self._timeout = timeout_seconds
        self._policy_guard = policy_guard

    async def execute(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        owner_id: UUID,
        tool_name: str,
        arguments: dict,
        call_id: UUID | None = None,
    ) -> ToolCall:
        # P5: gate sensitive tool calls behind the policy engine
        if self._policy_guard is not None:
            from qzdap_vault.actor import ActorContext

            await self._policy_guard.check(  # type: ignore[attr-defined]
                actor=ActorContext(
                    tenant_id=tenant_id,
                    workspace_id=workspace_id,
                    principal_id=owner_id,
                ),
                action=f"tool:execute:{tool_name}",
                resource={"tool": tool_name, "workspace_id": str(workspace_id)},
            )

        tool = await self._tools.get_by_name(tenant_id=tenant_id, name=tool_name)
        if tool is None:
            raise ToolNotFound(f"tool {tool_name!r} not found")
        if not tool.enabled:
            raise ToolDisabled(f"tool {tool_name!r} is disabled")

        call_id = call_id or uuid4()
        call = ToolCall.create(
            id=ToolCallId(call_id),
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            tool_name=tool_name,
            arguments=arguments,
        )
        await self._calls.add(call)
        await self._events.publish(
            call.raise_invoked_event(),
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            trace_id=current_trace_id(),
        )

        started = monotonic()
        try:
            result = await self._dispatch(tool.protocol, tool, arguments)
            latency_ms = int((monotonic() - started) * 1000)
            succeeded = call.succeed(result=result, latency_ms=latency_ms)
            await self._calls.add(succeeded)
            await self._events.publish(
                succeeded.raise_completed_event(latency_ms=latency_ms),
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                trace_id=current_trace_id(),
            )
            return succeeded
        except (TimeoutError, httpx.TimeoutException):
            latency_ms = int((monotonic() - started) * 1000)
            failed = call.fail(error_code="TOOL_CALL_TIMEOUT", latency_ms=latency_ms)
            await self._calls.add(failed)
            await self._events.publish(
                failed.raise_failed_event(error_code="TOOL_CALL_TIMEOUT"),
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                trace_id=current_trace_id(),
            )
            raise ToolCallTimeout(
                f"tool {tool_name!r} timed out after {self._timeout}s",
                code="TOOL_CALL_TIMEOUT",
            ) from None
        except InvalidToolSpecCallError:
            latency_ms = int((monotonic() - started) * 1000)
            failed = call.fail(error_code="INVALID_TOOL_SPEC", latency_ms=latency_ms)
            await self._calls.add(failed)
            await self._events.publish(
                failed.raise_failed_event(error_code="INVALID_TOOL_SPEC"),
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                trace_id=current_trace_id(),
            )
            raise
        except httpx.HTTPError:
            latency_ms = int((monotonic() - started) * 1000)
            failed = call.fail(error_code="UPSTREAM_UNAVAILABLE", latency_ms=latency_ms)
            await self._calls.add(failed)
            await self._events.publish(
                failed.raise_failed_event(error_code="UPSTREAM_UNAVAILABLE"),
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                trace_id=current_trace_id(),
            )
            raise UpstreamUnavailable(
                f"tool {tool_name!r} upstream unavailable",
                code="UPSTREAM_UNAVAILABLE",
            ) from None

    async def _dispatch(self, protocol: ToolProtocol, tool, arguments: dict) -> dict:
        if protocol is ToolProtocol.CUSTOM:
            # Strip internal routing keys before handing to the callable.
            clean = {k: v for k, v in arguments.items() if not k.startswith("__")}
            return await self._custom.invoke(name=tool.name, arguments=clean)

        if protocol is ToolProtocol.OPENAPI:
            operation = _pick_operation(tool.spec_operations, arguments)
            clean = {k: v for k, v in arguments.items() if not k.startswith("__")}
            base_url = (
                tool.spec.get("servers", [{}])[0].get("url")
                if tool.spec.get("servers")
                else ""
            )
            if not base_url:
                raise InvalidToolSpecCallError(
                    "openapi spec must contain a 'servers' entry with 'url'"
                )
            return await self._openapi.invoke(
                base_url=base_url,
                operation=operation,
                auth=tool.auth_config,
                arguments=clean,
                timeout=self._timeout,
            )

        if protocol is ToolProtocol.MCP:
            server_url = tool.spec.get("server_url")
            if not server_url:
                raise InvalidToolSpecCallError("mcp spec missing 'server_url'")
            mcp_tool_name = tool.spec.get("mcp_tool_name", tool.name)
            return await self._mcp.call_tool(
                server_url=server_url,
                tool_name=mcp_tool_name,
                arguments=arguments,
                auth=tool.auth_config,
                timeout=self._timeout,
            )

        raise InvalidToolSpecCallError(f"unsupported protocol {protocol!r}")
