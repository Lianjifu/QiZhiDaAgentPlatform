"""Use case: invoke a tool by name, dispatching to the right protocol.

Lifecycle:
  1. Look up Tool by (tenant_id, name). 404 if not found.
  2. Reject disabled tools with 409 TOOL_DISABLED.
  3. **占幂等的执行权** ✓（`tool_executions` ✓ —— 方案 §5.3.2 ✓）：
     - 抢到 → 继续执行 ✓；
     - 抢不到但**同参**且**已成功** → **直接返回既有结果** ✓（不重复执行 ✓）；
     - 抢不到但**异参** → **拒绝** ✓（`TOOL_IDEMPOTENCY_CONFLICT` ✓ —— 调用方的 bug ✓）；
     - 抢不到且**还在跑** → **拒绝** ✓（`TOOL_IN_PROGRESS` ✓ —— 不重复执行 ✓）。
  4. Persist a ToolCall(status=running). Emit ToolInvoked.
  5. Dispatch by protocol:
       - CUSTOM   → process-local registry
       - OPENAPI  → httpx POST to operation_id, with auth injection
       - MCP      → JSON-RPC over HTTP, tools/call
     **重试** ✓（指数退避 + jitter ✓ —— 仅限**幂等工具的瞬时错误** ✓）+
     **熔断** ✓（按工具名 ✓ —— 连续失败达阈值就熔断 ✓）。
  6. Persist success/failure row. Emit ToolCompleted / ToolFailed.
  7. Translate httpx errors to domain errors (504 / 502) without leaking
     upstream URLs / headers.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from time import monotonic
from uuid import UUID, uuid4

import httpx

from qzdap.modules.tool.application.idempotency import request_hash
from qzdap.modules.tool.application.ports import (
    CustomInvokerPort,
    EventPublisher,
    MCPRuntime,
    OpenAPIRuntime,
    ToolCallRepository,
    ToolExecutionPort,
    ToolRepository,
)
from qzdap.modules.tool.application.reliability import (
    CircuitBreaker,
    is_transient,
    retry_delay_ms,
)
from qzdap.modules.tool.application.tool_catalog import BUILTIN_TOOL_SPECS
from qzdap.modules.tool.domain import (
    SpecOperation,
    ToolCall,
    ToolDisabled,
    ToolNotFound,
    ToolProtocol,
)
from qzdap.modules.tool.domain.errors import (
    ToolCallTimeout,
    ToolExecutionInProgress,
    ToolIdempotencyConflict,
    ToolRateLimited,
    UpstreamUnavailable,
)
from qzdap_kernel.contextvars import current_trace_id
from qzdap_kernel.ids import TenantId, ToolCallId, TurnId, UserId, WorkspaceId

_log = logging.getLogger("qzdap.modules.tool")


def _is_idempotent(tool) -> bool:
    """**这个工具能不能重试** ✓（幂等才重试 ✓）。

    ⚠️ **内置工具看目录** ✓ —— ``tools`` 表里内置工具的 ``spec`` 是空的 ✓
    （种子只记「有这个工具」✓）→ 真契约在 ``BUILTIN_TOOL_SPECS`` ✓。
    """
    if bool((tool.spec or {}).get("idempotent")):
        return True
    catalog = BUILTIN_TOOL_SPECS.get(tool.name) or {}
    return bool(catalog.get("idempotent"))


def _pick_operation(operations: list[SpecOperation], arguments: dict) -> SpecOperation:
    """Pick the single operation referenced by `arguments["__operation_id"]`.

    The HTTP DTO copies the operationId into `arguments` so we can route
    without inventing a separate field on the request body."""
    op_id = arguments.get("__operation_id")
    if not isinstance(op_id, str) or not op_id:
        raise InvalidToolSpecCallError("openapi invocation requires '__operation_id' in arguments")
    for op in operations:
        if op.operation_id == op_id:
            return op
    raise InvalidToolSpecCallError(f"unknown operation_id {op_id!r}")


class InvalidToolSpecCallError(Exception):
    """Local sentinel — translated to 422 by the HTTP layer."""


@dataclass(slots=True, frozen=True)
class _CallContext:
    """**一次调用的身份上下文** ✓ —— 内置工具用它做审计与作用域判断 ✓。"""

    tenant_id: TenantId
    workspace_id: WorkspaceId
    call_id: ToolCallId
    actor_id: UserId


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
        executions: ToolExecutionPort | None = None,
        breaker: CircuitBreaker | None = None,
        max_attempts: int = 3,
    ) -> None:
        self._tools = tools
        self._calls = calls
        self._custom = custom
        self._openapi = openapi
        self._mcp = mcp
        self._events = events
        self._timeout = timeout_seconds
        self._policy_guard = policy_guard
        # ⚠️ **幂等的唯一权威** ✓（`tool_executions` ✓ —— 跨 worker 有效 ✓）。
        # ⚠️ **没有它就退回「无幂等」** ✓（不静默假装有幂等 ✗✗）。
        self._executions = executions
        # ⚠️ **熔断器必须是进程内共享的那一个** ✓ —— 每请求新建一个 = 永远
        # 不熔断 ✗✗（那是「有熔断代码但没熔断」✗）。组合根持有单例 ✓。
        self._breaker = breaker
        self._max_attempts = max(1, max_attempts)

    async def execute(
        self,
        *,
        tenant_id: TenantId,
        workspace_id: WorkspaceId,
        owner_id: UserId,
        tool_name: str,
        arguments: dict,
        call_id: ToolCallId | None = None,
        turn_id: TurnId | None = None,
        idempotency_key: str | None = None,
    ) -> ToolCall:
        # P5: gate sensitive tool calls behind the policy engine
        if self._policy_guard is not None:
            from qzdap_vault.actor import ActorContext

            await self._policy_guard.check(  # type: ignore[attr-defined]
                actor=ActorContext(
                    tenant_id=TenantId(tenant_id),
                    workspace_id=WorkspaceId(workspace_id) if workspace_id is not None else None,
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

        call_id = call_id or ToolCallId(uuid4())

        # ── 幂等：先占执行权 ✓（§5.3.2 ✓） ──────────────────────────────
        fingerprint = request_hash(arguments)
        reused = await self._claim(
            idempotency_key=idempotency_key,
            fingerprint=fingerprint,
            call_id=call_id,
            turn_id=turn_id,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
        )
        if reused is not None:
            # ⚠️ **同参且已成功 → 直接返回既有结果** ✓（不重复执行 ✓）
            return reused

        call = ToolCall.create(
            id=call_id,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            tool_name=tool_name,
            arguments=arguments,
        )
        # Per-call tenant context: built-in tools (web_search / http_fetch)
        # need it for audit logging. Stored only for the duration of this
        # invocation; the use case is otherwise stateless.
        self._last_call_ctx = _CallContext(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            call_id=call_id,
            actor_id=owner_id,
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
            result = await self._run_with_retry(tool, arguments)
            latency_ms = int((monotonic() - started) * 1000)
            succeeded = call.succeed(result=result, latency_ms=latency_ms)
            await self._calls.add(succeeded)
            await self._events.publish(
                succeeded.raise_completed_event(latency_ms=latency_ms),
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                trace_id=current_trace_id(),
            )
            await self._finish_execution(
                idempotency_key=idempotency_key,
                status="succeeded",
                result_ref=str(call_id),
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
            await self._finish_execution(
                idempotency_key=idempotency_key,
                status="timeout",
                result_ref=str(call_id),
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
            await self._finish_execution(
                idempotency_key=idempotency_key,
                status="failed",
                result_ref=str(call_id),
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
            await self._finish_execution(
                idempotency_key=idempotency_key,
                status="failed",
                result_ref=str(call_id),
            )
            raise UpstreamUnavailable(
                f"tool {tool_name!r} upstream unavailable",
                code="UPSTREAM_UNAVAILABLE",
            ) from None

    # ── 幂等 ────────────────────────────────────────────────────────────

    async def _claim(
        self,
        *,
        idempotency_key: str | None,
        fingerprint: str,
        call_id: ToolCallId,
        turn_id: TurnId | None,
        tenant_id: TenantId,
        workspace_id: WorkspaceId,
    ) -> ToolCall | None:
        """**占执行权** ✓ —— 返回**可复用的既有调用** ✓（没有就是 ``None`` ✓）。

        ⚠️ **三条路** ✓（§5.3.2 ✓）：
        1. **抢到** → 返回 ``None`` ✓（继续执行 ✓）；
        2. **同参且已成功** → 返回既有调用 ✓（调用方直接返回它 ✓ —— **不重复执行** ✓）；
        3. **异参** → **拒绝** ✓（`TOOL_IDEMPOTENCY_CONFLICT` ✓）；
        4. **还在跑** → **拒绝** ✓（`TOOL_IN_PROGRESS` ✓ —— **不重复执行** ✓）。
        """
        if self._executions is None or not idempotency_key or turn_id is None:
            # ⚠️ **没有幂等设施就不假装有** ✓（不静默降级成「看起来幂等」✗✗）
            return None
        claim = await self._executions.begin(
            idempotency_key=idempotency_key,
            request_hash=fingerprint,
            tool_call_id=str(call_id),
            turn_id=turn_id,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
        )
        if claim.claimed:
            return None
        if claim.request_hash and claim.request_hash != fingerprint:
            raise ToolIdempotencyConflict(
                f"idempotency key {idempotency_key!r} was used with different arguments",
                code="TOOL_IDEMPOTENCY_CONFLICT",
            )
        if claim.status == "succeeded" and claim.result_ref:
            try:
                existing = await self._calls.get(ToolCallId(UUID(claim.result_ref)))
            except (TypeError, ValueError):
                existing = None
            if existing is not None:
                return existing
        raise ToolExecutionInProgress(
            f"tool call with idempotency key {idempotency_key!r} is already running",
            code="TOOL_IN_PROGRESS",
        )

    async def _finish_execution(
        self,
        *,
        idempotency_key: str | None,
        status: str,
        result_ref: str | None,
    ) -> None:
        """**收尾幂等记录** ✓（状态 ✓ + 结果指针 ✓）。"""
        if self._executions is None or not idempotency_key:
            return
        try:
            await self._executions.finish(
                idempotency_key=idempotency_key, status=status, result_ref=result_ref
            )
        except Exception:
            _log.exception("tool execution finalize failed")

    # ── 重试与熔断 ──────────────────────────────────────────────────────

    async def _run_with_retry(self, tool, arguments: dict) -> dict:
        """**执行 + 重试 + 熔断** ✓（§5.3.3 ✓）。

        ⚠️ **只重试「幂等工具的瞬时错误」** ✓ —— 重试一个有副作用的工具可能
        **执行两次** ✗✗（那正是幂等要防的事 ✗）。
        """
        attempts = self._max_attempts
        idempotent = _is_idempotent(tool)
        last_error: BaseException | None = None
        for attempt in range(1, attempts + 1):
            if self._breaker is not None and self._breaker.is_open(tool.name):
                raise ToolRateLimited(
                    f"tool {tool.name!r} is circuit-broken",
                    code="TOOL_RATE_LIMITED",
                    retry_after_ms=self._breaker.retry_after_ms(tool.name),
                )
            try:
                result = await self._dispatch(tool.protocol, tool, arguments)
            except Exception as exc:
                last_error = exc
                if self._breaker is not None:
                    self._breaker.record_failure(tool.name)
                if not idempotent or not is_transient(exc) or attempt >= attempts:
                    raise
                delay_ms = retry_delay_ms(attempt)
                await asyncio.sleep(delay_ms / 1000)
                continue
            if self._breaker is not None:
                self._breaker.record_success(tool.name)
            return result
        # ⚠️ **走到这里说明循环没返回** ✓ —— 只可能是异常 ✓
        raise (
            last_error
            if last_error is not None
            else RuntimeError(f"tool {tool.name!r} produced no result")
        )

    async def _dispatch(self, protocol: ToolProtocol, tool, arguments: dict) -> dict:
        if protocol is ToolProtocol.CUSTOM:
            # Strip internal routing keys before handing to the callable.
            clean = {k: v for k, v in arguments.items() if not k.startswith("__")}
            ctx = self._last_call_ctx
            if ctx is None:
                raise RuntimeError("custom tool dispatched without a call context")
            return await self._custom.invoke(
                name=tool.name,
                arguments=clean,
                tenant_id=ctx.tenant_id,
                workspace_id=ctx.workspace_id,
                call_id=ctx.call_id,
                actor_id=ctx.actor_id,
            )

        if protocol is ToolProtocol.OPENAPI:
            operation = _pick_operation(tool.spec_operations, arguments)
            clean = {k: v for k, v in arguments.items() if not k.startswith("__")}
            base_url = (
                tool.spec.get("servers", [{}])[0].get("url") if tool.spec.get("servers") else ""
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
