"""工具执行的**幂等 / 重试 / 熔断** ✓（Agent 方案 §5.3.2 / §5.3.3 ✓）。

验收三条 ✓：**同键同参不重复执行** ✓ / **同键异参明确拒绝** ✓ /
**幂等工具的瞬时错误会重试、非幂等的不重试** ✓。
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest
from _tool_unit_in_memory import (  # type: ignore[import-not-found]
    CollectingEventPublisher,
    FakeCustomInvoker,
    FakeMCPRuntime,
    FakeOpenAPIRuntime,
    InMemoryToolCallRepository,
    InMemoryToolRepository,
)
from qzdap_schema.ids import TenantId, ToolId, WorkspaceId

from qzdap.modules.tool.application.idempotency import request_hash
from qzdap.modules.tool.application.ports import ToolExecutionClaim
from qzdap.modules.tool.application.reliability import (
    CircuitBreaker,
    is_transient,
    retry_delay_ms,
)
from qzdap.modules.tool.application.use_cases.invoke_tool import InvokeToolUseCase
from qzdap.modules.tool.domain import ToolProtocol
from qzdap.modules.tool.domain.errors import (
    ToolCallTimeout,
    ToolExecutionInProgress,
    ToolIdempotencyConflict,
    ToolRateLimited,
)

_TENANT = TenantId(uuid4())
_WORKSPACE = WorkspaceId(uuid4())
_OWNER = uuid4()
_TURN = uuid4()


def _tool(name: str = "echo", *, spec: dict[str, Any] | None = None, enabled: bool = True):
    from qzdap.modules.tool.domain import Tool

    return Tool.create(
        id=ToolId(uuid4()),
        tenant_id=_TENANT,
        workspace_id=_WORKSPACE,
        name=name,
        description="",
        protocol=ToolProtocol.CUSTOM,
        spec=spec or {},
        enabled=enabled,
    )


class _FakeExecutions:
    """`tool_executions` 的内存替身 ✓。"""

    def __init__(self, claim: ToolExecutionClaim | None = None) -> None:
        self.claim = claim
        self.begins: list[dict[str, Any]] = []
        self.finishes: list[dict[str, Any]] = []

    async def begin(self, **kwargs: Any) -> ToolExecutionClaim:
        self.begins.append(kwargs)
        return self.claim or ToolExecutionClaim(claimed=True)

    async def finish(self, **kwargs: Any) -> None:
        self.finishes.append(kwargs)


def _use_case(
    *,
    tools: InMemoryToolRepository,
    calls: InMemoryToolCallRepository,
    custom: FakeCustomInvoker,
    executions: _FakeExecutions | None = None,
    breaker: CircuitBreaker | None = None,
    max_attempts: int = 3,
) -> InvokeToolUseCase:
    return InvokeToolUseCase(
        tools=tools,
        calls=calls,
        custom=custom,
        openapi=FakeOpenAPIRuntime(),
        mcp=FakeMCPRuntime(),
        events=CollectingEventPublisher(),
        executions=executions,
        breaker=breaker,
        max_attempts=max_attempts,
    )


class TestRequestHash:
    def test_the_key_order_does_not_change_the_hash(self) -> None:
        assert request_hash({"a": 1, "b": 2}) == request_hash({"b": 2, "a": 1})

    def test_different_arguments_have_different_hashes(self) -> None:
        assert request_hash({"a": 1}) != request_hash({"a": 2})

    def test_the_chinese_parameters_are_stable(self) -> None:
        assert request_hash({"q": "搜一下"}) == request_hash({"q": "搜一下"})


class TestIdempotency:
    @pytest.mark.asyncio
    async def test_the_same_key_with_the_same_arguments_reuses_the_result(self) -> None:
        """**同键同参 → 不重复执行** ✓（复用既有结果 ✓）。"""
        tools = InMemoryToolRepository()
        calls = InMemoryToolCallRepository()
        tool = _tool()
        await tools.add(tool)
        custom = FakeCustomInvoker({"echo": _echo("hi")})
        existing = calls  # 既有调用
        executions = _FakeExecutions(
            ToolExecutionClaim(
                claimed=False,
                status="succeeded",
                request_hash=request_hash({"text": "hi"}),
                result_ref=str(uuid4()),
            )
        )
        # 既有调用放进去（复用它 ✓）
        from qzdap.modules.tool.domain import ToolCall

        old = ToolCall.create(
            id=uuid4(),
            tenant_id=_TENANT,
            workspace_id=_WORKSPACE,
            tool_name="echo",
            arguments={"text": "hi"},
        )
        await existing.add(old.succeed(result={"echo": "hi"}, latency_ms=1))
        executions.claim = ToolExecutionClaim(
            claimed=False,
            status="succeeded",
            request_hash=request_hash({"text": "hi"}),
            result_ref=str(old.id),
        )
        use_case = _use_case(
            tools=tools, calls=calls, custom=custom, executions=executions
        )
        result = await use_case.execute(
            tenant_id=_TENANT,
            workspace_id=_WORKSPACE,
            owner_id=_OWNER,
            tool_name="echo",
            arguments={"text": "hi"},
            turn_id=_TURN,
            idempotency_key="k1",
        )
        assert result.result == {"echo": "hi"}
        assert custom.last_name is None, "命中幂等就不该再执行一次"

    @pytest.mark.asyncio
    async def test_the_same_key_with_different_arguments_is_refused(self) -> None:
        """**同键异参 → 明确拒绝** ✓（不静默返回旧结果 ✓）。"""
        tools = InMemoryToolRepository()
        calls = InMemoryToolCallRepository()
        await tools.add(_tool())
        executions = _FakeExecutions(
            ToolExecutionClaim(
                claimed=False,
                status="succeeded",
                request_hash=request_hash({"text": "别的参数"}),
                result_ref=str(uuid4()),
            )
        )
        use_case = _use_case(
            tools=tools,
            calls=calls,
            custom=FakeCustomInvoker({"echo": _echo("hi")}),
            executions=executions,
        )
        with pytest.raises(ToolIdempotencyConflict):
            await use_case.execute(
                tenant_id=_TENANT,
                workspace_id=_WORKSPACE,
                owner_id=_OWNER,
                tool_name="echo",
                arguments={"text": "hi"},
                turn_id=_TURN,
                idempotency_key="k1",
            )

    @pytest.mark.asyncio
    async def test_a_running_call_is_not_executed_again(self) -> None:
        """**同键且还在跑 → 拒绝** ✓（不重复执行 ✓）。"""
        tools = InMemoryToolRepository()
        calls = InMemoryToolCallRepository()
        await tools.add(_tool())
        executions = _FakeExecutions(
            ToolExecutionClaim(
                claimed=False,
                status="running",
                request_hash=request_hash({"text": "hi"}),
                result_ref=None,
            )
        )
        custom = FakeCustomInvoker({"echo": _echo("hi")})
        use_case = _use_case(
            tools=tools, calls=calls, custom=custom, executions=executions
        )
        with pytest.raises(ToolExecutionInProgress):
            await use_case.execute(
                tenant_id=_TENANT,
                workspace_id=_WORKSPACE,
                owner_id=_OWNER,
                tool_name="echo",
                arguments={"text": "hi"},
                turn_id=_TURN,
                idempotency_key="k1",
            )
        assert custom.last_name is None

    @pytest.mark.asyncio
    async def test_the_execution_is_finished_with_the_result_pointer(self) -> None:
        """**收尾写状态 + 结果指针** ✓（指针不是正文 ✓）。"""
        tools = InMemoryToolRepository()
        calls = InMemoryToolCallRepository()
        await tools.add(_tool())
        executions = _FakeExecutions()
        use_case = _use_case(
            tools=tools,
            calls=calls,
            custom=FakeCustomInvoker({"echo": _echo("hi")}),
            executions=executions,
        )
        await use_case.execute(
            tenant_id=_TENANT,
            workspace_id=_WORKSPACE,
            owner_id=_OWNER,
            tool_name="echo",
            arguments={"text": "hi"},
            turn_id=_TURN,
            idempotency_key="k1",
        )
        assert executions.finishes[0]["status"] == "succeeded"
        assert executions.finishes[0]["result_ref"]

    @pytest.mark.asyncio
    async def test_without_a_turn_there_is_no_idempotency(self) -> None:
        """**没有轮次就没有幂等** ✓（不静默假装有 ✓）。"""
        tools = InMemoryToolRepository()
        calls = InMemoryToolCallRepository()
        await tools.add(_tool())
        executions = _FakeExecutions()
        custom = FakeCustomInvoker({"echo": _echo("hi")})
        use_case = _use_case(
            tools=tools, calls=calls, custom=custom, executions=executions
        )
        await use_case.execute(
            tenant_id=_TENANT,
            workspace_id=_WORKSPACE,
            owner_id=_OWNER,
            tool_name="echo",
            arguments={"text": "hi"},
            idempotency_key="k1",
        )
        assert executions.begins == []
        assert custom.last_name == "echo"


class TestRetryAndBreaker:
    @pytest.mark.asyncio
    async def test_an_idempotent_tool_is_retried_on_a_transient_error(self) -> None:
        """**幂等工具的瞬时错误会重试** ✓。"""
        tools = InMemoryToolRepository()
        calls = InMemoryToolCallRepository()
        await tools.add(_tool("flaky", spec={"idempotent": True}))
        attempts = {"n": 0}

        async def _flaky(arguments: dict[str, Any], **_: Any) -> dict[str, Any]:
            attempts["n"] += 1
            if attempts["n"] < 3:
                raise TimeoutError("boom")
            return {"ok": True}

        custom = FakeCustomInvoker({"flaky": _flaky})
        use_case = _use_case(
            tools=tools, calls=calls, custom=custom, max_attempts=3
        )
        result = await use_case.execute(
            tenant_id=_TENANT,
            workspace_id=_WORKSPACE,
            owner_id=_OWNER,
            tool_name="flaky",
            arguments={},
        )
        assert result.result == {"ok": True}
        assert attempts["n"] == 3

    @pytest.mark.asyncio
    async def test_a_non_idempotent_tool_is_not_retried(self) -> None:
        """**有副作用的工具不重试** ✓（重试它可能执行两次 ✗✗）。"""
        tools = InMemoryToolRepository()
        calls = InMemoryToolCallRepository()
        await tools.add(_tool("write", spec={}))
        attempts = {"n": 0}

        async def _boom(arguments: dict[str, Any], **_: Any) -> dict[str, Any]:
            attempts["n"] += 1
            raise TimeoutError("boom")

        custom = FakeCustomInvoker({"write": _boom})
        use_case = _use_case(
            tools=tools, calls=calls, custom=custom, max_attempts=3
        )
        with pytest.raises(ToolCallTimeout):
            await use_case.execute(
                tenant_id=_TENANT,
                workspace_id=_WORKSPACE,
                owner_id=_OWNER,
                tool_name="write",
                arguments={},
            )
        assert attempts["n"] == 1

    @pytest.mark.asyncio
    async def test_the_breaker_stops_a_failing_tool(self) -> None:
        """**连续失败达阈值就熔断** ✓（之后直接拒绝 ✓）。"""
        tools = InMemoryToolRepository()
        calls = InMemoryToolCallRepository()
        await tools.add(_tool("down", spec={"idempotent": True}))
        breaker = CircuitBreaker(threshold=2, cooldown_seconds=60)
        attempts = {"n": 0}

        async def _boom(arguments: dict[str, Any], **_: Any) -> dict[str, Any]:
            attempts["n"] += 1
            raise TimeoutError("boom")

        custom = FakeCustomInvoker({"down": _boom})
        use_case = _use_case(
            tools=tools,
            calls=calls,
            custom=custom,
            breaker=breaker,
            max_attempts=1,
        )
        for _ in range(2):
            with pytest.raises(ToolCallTimeout):
                await use_case.execute(
                    tenant_id=_TENANT,
                    workspace_id=_WORKSPACE,
                    owner_id=_OWNER,
                    tool_name="down",
                    arguments={},
                )
        with pytest.raises(ToolRateLimited):
            await use_case.execute(
                tenant_id=_TENANT,
                workspace_id=_WORKSPACE,
                owner_id=_OWNER,
                tool_name="down",
                arguments={},
            )
        assert attempts["n"] == 2, "熔断之后不该再打上游"


class TestReliabilityHelpers:
    def test_the_timeouts_are_transient(self) -> None:
        assert is_transient(TimeoutError()) is True
        assert is_transient(ValueError()) is False

    def test_the_delay_grows_and_stays_bounded(self) -> None:
        first = retry_delay_ms(1)
        later = retry_delay_ms(5)
        assert first <= later
        assert later <= 5_000 * 1.2 + 1


def _echo(text: str):
    async def _fn(arguments: dict[str, Any], **_: Any) -> dict[str, Any]:
        return {"echo": arguments.get("text", text)}

    return _fn


__all__ = ["UUID"]
