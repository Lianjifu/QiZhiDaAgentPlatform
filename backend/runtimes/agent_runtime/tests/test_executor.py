"""Tests for InMemoryToolExecutor (§5.8)."""

from __future__ import annotations

import asyncio

import pytest
from pydantic import BaseModel

from qzdap_agent_runtime.execution import (
    InMemoryToolExecutor,
    ToolArgumentError,
    ToolRateLimitError,
    ToolTimeoutError,
)
from qzdap_agent_runtime.ports import ToolMeta, ToolExecutor


class _Args(BaseModel):
    query: str = "default"


def _meta(
    *,
    name: str = "t",
    risk: str = "low",
    idempotent: bool = True,
    timeout_ms: int = 1000,
    max_retries: int = 2,
    backoff_ms: int = 10,
    requires_approval: bool = False,
    side_effect: bool = False,
) -> ToolMeta:
    return ToolMeta(
        name=name, description="t", args_schema=_Args,
        risk=risk, requires_approval=requires_approval,
        timeout_ms=timeout_ms, max_retries=max_retries,
        backoff_ms=backoff_ms, idempotent=idempotent,
        side_effect=side_effect,
    )


def test_executor_satisfies_protocol() -> None:
    assert isinstance(InMemoryToolExecutor(), ToolExecutor)


class TestSuccessfulExecution:
    async def test_sync_tool_returns_result(self) -> None:
        exe = InMemoryToolExecutor()
        meta = _meta(timeout_ms=1000)
        result = await exe.execute(
            tool_call_id="tc-1",
            tool=lambda query: f"ok:{query}",
            arguments={"query": "hi"},
            meta=meta,
            turn_id="t-1",
            idempotency_key="ik-1",
        )
        assert result["is_error"] is False
        assert result["result"] == "ok:hi"
        assert result["latency_ms"] >= 0

    async def test_async_tool_returns_result(self) -> None:
        exe = InMemoryToolExecutor()
        meta = _meta()

        async def async_tool(query: str) -> str:
            await asyncio.sleep(0.01)
            return f"async:{query}"

        result = await exe.execute(
            tool_call_id="tc-1",
            tool=async_tool,
            arguments={"query": "hi"},
            meta=meta,
            turn_id="t-1",
            idempotency_key="ik-1",
        )
        assert result["is_error"] is False
        assert "async:hi" in result["result"]


class TestTimeout:
    async def test_timeout_returns_TOOL_TIMEOUT(self) -> None:
        exe = InMemoryToolExecutor()
        meta = _meta(timeout_ms=50, idempotent=False)

        async def slow_tool(query: str) -> str:
            await asyncio.sleep(0.5)
            return query

        result = await exe.execute(
            tool_call_id="tc-1",
            tool=slow_tool,
            arguments={"query": "hi"},
            meta=meta,
            turn_id="t-1",
            idempotency_key="ik-1",
        )
        assert result["is_error"] is True
        assert result["error_code"] == "TOOL_TIMEOUT"
        # 记录里 status 必须是 timeout
        record = exe.records[-1]
        assert record.status == "timeout"


class TestArgumentValidation:
    async def test_non_dict_arguments_returns_TOOL_ARGUMENT_INVALID(self) -> None:
        exe = InMemoryToolExecutor()
        meta = _meta()
        result = await exe.execute(
            tool_call_id="tc-1",
            tool=lambda **kwargs: "x",
            arguments="not a dict",  # type: ignore[arg-type]
            meta=meta,
            turn_id="t-1",
            idempotency_key="ik-1",
        )
        assert result["is_error"] is True
        assert result["error_code"] == "TOOL_ARGUMENT_INVALID"

    async def test_tool_raising_ToolArgumentError_does_not_retry(self) -> None:
        """参数错误不重试 (按 §5.8 决策)。"""
        exe = InMemoryToolExecutor()
        meta = _meta(idempotent=True, max_retries=5)
        call_count = 0

        def bad_tool(query: str) -> str:
            nonlocal call_count
            call_count += 1
            raise ToolArgumentError("missing required field", tool_name="t")

        result = await exe.execute(
            tool_call_id="tc-1",
            tool=bad_tool,
            arguments={"query": "hi"},
            meta=meta,
            turn_id="t-1",
            idempotency_key="ik-1",
        )
        assert result["is_error"] is True
        assert result["error_code"] == "TOOL_ARGUMENT_INVALID"
        # 仅调用 1 次, 不重试
        assert call_count == 1


class TestRetry:
    async def test_idempotent_retries_until_success(self) -> None:
        exe = InMemoryToolExecutor()
        meta = _meta(idempotent=True, max_retries=3, backoff_ms=10)
        call_count = 0

        def flaky_tool(query: str) -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise RuntimeError("transient error")
            return f"ok:{query}"

        result = await exe.execute(
            tool_call_id="tc-1",
            tool=flaky_tool,
            arguments={"query": "hi"},
            meta=meta,
            turn_id="t-1",
            idempotency_key="ik-1",
        )
        assert result["is_error"] is False
        assert result["result"] == "ok:hi"
        # 调用 3 次（2 次失败 + 1 次成功）
        assert call_count == 3

    async def test_non_idempotent_does_not_retry(self) -> None:
        """§5.8: 非幂等工具不自动重试。"""
        exe = InMemoryToolExecutor()
        meta = _meta(idempotent=False, max_retries=5, backoff_ms=10)
        call_count = 0

        def fail_tool(query: str) -> str:
            nonlocal call_count
            call_count += 1
            raise RuntimeError("boom")

        result = await exe.execute(
            tool_call_id="tc-1",
            tool=fail_tool,
            arguments={"query": "hi"},
            meta=meta,
            turn_id="t-1",
            idempotency_key="ik-1",
        )
        assert result["is_error"] is True
        # 仅 1 次调用
        assert call_count == 1


class TestIdempotencyCache:
    async def test_same_idempotency_key_returns_cached(self) -> None:
        exe = InMemoryToolExecutor()
        meta = _meta()
        call_count = 0

        def counter_tool(query: str) -> str:
            nonlocal call_count
            call_count += 1
            return f"result-{call_count}"

        r1 = await exe.execute(
            tool_call_id="tc-1",
            tool=counter_tool,
            arguments={"query": "hi"},
            meta=meta,
            turn_id="t-1",
            idempotency_key="ik-same",
        )
        r2 = await exe.execute(
            tool_call_id="tc-2",
            tool=counter_tool,
            arguments={"query": "hi"},
            meta=meta,
            turn_id="t-1",
            idempotency_key="ik-same",  # 同 key
        )
        # 第一次执行
        assert r1["is_error"] is False
        assert r1["result"] == "result-1"
        # 第二次命中缓存, 不再调用
        assert r2["is_error"] is False
        assert r2["result"] == "result-1"
        assert r2.get("from_cache") is True
        assert call_count == 1

    async def test_different_idempotency_keys_call_twice(self) -> None:
        exe = InMemoryToolExecutor()
        meta = _meta()
        call_count = 0

        def counter_tool(query: str) -> str:
            nonlocal call_count
            call_count += 1
            return f"r-{call_count}"

        await exe.execute(
            tool_call_id="tc-1", tool=counter_tool,
            arguments={"query": "hi"}, meta=meta, turn_id="t-1",
            idempotency_key="ik-A",
        )
        await exe.execute(
            tool_call_id="tc-2", tool=counter_tool,
            arguments={"query": "hi"}, meta=meta, turn_id="t-1",
            idempotency_key="ik-B",
        )
        assert call_count == 2


class TestRateLimitCircuitBreaker:
    async def test_three_rate_limits_trips_circuit(self) -> None:
        """连续 3 次限流后熔断。"""
        exe = InMemoryToolExecutor()
        meta = _meta()

        def rate_limited_tool(query: str) -> str:
            raise ToolRateLimitError("tc", retry_after_ms=1000)

        for i in range(3):
            await exe.execute(
                tool_call_id=f"tc-{i}",
                tool=rate_limited_tool,
                arguments={"query": "x"},
                meta=meta,
                turn_id="t-1",
                idempotency_key=f"ik-{i}",
            )

        # 第 4 次直接走熔断路径（不调用 tool）
        result = await exe.execute(
            tool_call_id="tc-4",
            tool=lambda q: "should not be called",
            arguments={"query": "x"},
            meta=meta,
            turn_id="t-1",
            idempotency_key="ik-4",
        )
        assert result["is_error"] is True
        assert result["error_code"] == "TOOL_RATE_LIMITED"
        assert "circuit" in result["error_message"].lower()


class TestRecordKeeping:
    async def test_record_tracks_attempts_latency(self) -> None:
        exe = InMemoryToolExecutor()
        meta = _meta(idempotent=True, max_retries=2, backoff_ms=10)

        def flaky(query: str) -> str:
            raise RuntimeError("boom")

        result = await exe.execute(
            tool_call_id="tc-1",
            tool=flaky,
            arguments={"query": "hi"},
            meta=meta,
            turn_id="t-1",
            idempotency_key="ik-1",
        )
        record = exe.records[-1]
        assert record.tool_call_id == "tc-1"
        assert record.tool_name == "t"
        assert record.request_hash  # 非空
        assert record.attempts == 3  # 1 + 2 retries
        assert record.latency_ms >= 0
        assert record.is_error is True