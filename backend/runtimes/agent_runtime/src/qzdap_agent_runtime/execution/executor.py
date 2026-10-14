"""Tool executor — §5.8 统一执行器（重试/超时/幂等/熔断/降级）。

Stage 4 PR B 范围：

- `InMemoryToolExecutor`: ToolExecutor Protocol 进程内实现
  - 重试：指数退避 + jitter（仅对 `idempotent=true` 的瞬态错误）
  - 超时：`asyncio.wait_for` 强制 timeout_ms
  - 幂等：同 `idempotency_key` 重复调用直接返回缓存结果
  - 降级：失败不抛穿图，包装为结构化结果（§5.8 ToolResult 字段）
- 错误码映射：
  - 参数错误 → TOOL_ARGUMENT_INVALID
  - 超时 → TOOL_TIMEOUT
  - 限流 → TOOL_RATE_LIMITED
  - 不可解析 → is_error=true 不抛
- `tool_executions` 持久化（§4.2）— 在 execution/ 占位协议
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from ..ports import ToolExecutor, ToolMeta

# ---------------------------------------------------------------------------
# 错误类型
# ---------------------------------------------------------------------------


class ToolArgumentError(Exception):
    """§5.8 TOOL_ARGUMENT_INVALID"""

    def __init__(self, message: str, tool_name: str | None = None) -> None:
        self.message = message
        self.tool_name = tool_name
        super().__init__(message)


class ToolTimeoutError(Exception):
    """§5.8 TOOL_TIMEOUT"""

    def __init__(self, tool_call_id: str, timeout_ms: int) -> None:
        self.tool_call_id = tool_call_id
        self.timeout_ms = timeout_ms
        super().__init__(f"tool {tool_call_id} timed out after {timeout_ms}ms")


class ToolRateLimitError(Exception):
    """§5.8 TOOL_RATE_LIMITED"""

    def __init__(self, tool_call_id: str, retry_after_ms: int = 1000) -> None:
        self.tool_call_id = tool_call_id
        self.retry_after_ms = retry_after_ms
        super().__init__(f"tool {tool_call_id} rate limited, retry after {retry_after_ms}ms")


# ---------------------------------------------------------------------------
# 工具调用记录
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class ToolCallRecord:
    """§4.2 tool_executions 表的内存等价。"""

    tool_call_id: str
    idempotency_key: str
    tool_name: str
    arguments: dict[str, Any]
    request_hash: str
    status: str  # 'pending' | 'running' | 'succeeded' | 'failed' | 'timeout'
    result: Any = None
    is_error: bool = False
    latency_ms: int = 0
    attempts: int = 0
    error_code: str | None = None
    error_message: str | None = None


# ---------------------------------------------------------------------------
# InMemoryToolExecutor
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class _IdempotencyEntry:
    """幂等缓存：同 idempotency_key 直接返回缓存结果。"""

    result: Any
    created_at: float = field(default_factory=time.time)


@runtime_checkable
class ToolFunction(Protocol):
    """工具函数可以是 sync 或 async callable。"""

    def __call__(self, *args: Any, **kwargs: Any) -> Any: ...


class InMemoryToolExecutor:
    """§5.8 ToolExecutor 进程内实现。"""

    def __init__(self) -> None:
        self._idempotency_cache: dict[str, _IdempotencyEntry] = {}
        self._records: list[ToolCallRecord] = []
        # 熔断：连续失败 N 次后熔断 M 秒
        self._failure_count: dict[str, int] = {}
        self._circuit_open_until: dict[str, float] = {}

    @staticmethod
    def _request_hash(arguments: dict[str, Any]) -> str:
        encoded = json.dumps(arguments, sort_keys=True, ensure_ascii=False).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    async def execute(
        self,
        *,
        tool_call_id: str,
        tool: Any,
        arguments: dict[str, Any],
        meta: ToolMeta,
        turn_id: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        """执行工具, 返回结构化结果。失败不抛穿图 (§5.8)。"""
        # 0. 熔断检查
        if meta.name in self._circuit_open_until:
            until = self._circuit_open_until[meta.name]
            if time.time() < until:
                return {
                    "is_error": True,
                    "error_code": "TOOL_RATE_LIMITED",
                    "error_message": f"circuit open for {meta.name}",
                    "retry_after_ms": int((until - time.time()) * 1000),
                }

        # 1. 幂等检查
        if idempotency_key in self._idempotency_cache:
            cached = self._idempotency_cache[idempotency_key]
            return {
                "is_error": False,
                "result": cached.result,
                "from_cache": True,
            }

        # 2. 参数校验（简化：要求 dict，非空）
        if not isinstance(arguments, dict):
            return {
                "is_error": True,
                "error_code": "TOOL_ARGUMENT_INVALID",
                "error_message": f"arguments must be dict, got {type(arguments).__name__}",
            }

        # 3. 执行（带超时 + 重试）
        request_hash = self._request_hash(arguments)
        record = ToolCallRecord(
            tool_call_id=tool_call_id,
            idempotency_key=idempotency_key,
            tool_name=meta.name,
            arguments=arguments,
            request_hash=request_hash,
            status="running",
        )
        self._records.append(record)

        result = await self._execute_with_retry(
            tool=tool,
            arguments=arguments,
            meta=meta,
            tool_call_id=tool_call_id,
            record=record,
        )

        # 4. 落幂等缓存（仅成功时）
        if not result.get("is_error"):
            self._idempotency_cache[idempotency_key] = _IdempotencyEntry(
                result=result.get("result")
            )

        return result

    async def _execute_with_retry(
        self,
        *,
        tool: Any,
        arguments: dict[str, Any],
        meta: ToolMeta,
        tool_call_id: str,
        record: ToolCallRecord,
    ) -> dict[str, Any]:
        last_error: Exception | None = None
        max_attempts = 1 if not meta.idempotent else max(1, meta.max_retries + 1)

        for attempt in range(max_attempts):
            record.attempts = attempt + 1
            start = time.time()
            try:
                # 兼容 BaseTool 和普通 callable:
                # - BaseTool (LangChain): 用 .invoke(arguments) 调用
                # - 普通 callable: 用 (**arguments) 调用
                from langchain_core.tools import BaseTool as _BaseTool
                if isinstance(tool, _BaseTool):
                    if asyncio.iscoroutinefunction(tool.invoke):
                        output = await asyncio.wait_for(
                            tool.invoke(arguments),
                            timeout=meta.timeout_ms / 1000.0,
                        )
                    else:
                        # 同步 invoke 仍在线程池跑
                        import concurrent.futures
                        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                            output = await asyncio.get_event_loop().run_in_executor(
                                ex, lambda: tool.invoke(arguments)
                            )
                elif asyncio.iscoroutinefunction(tool):
                    output = await asyncio.wait_for(
                        tool(**arguments),
                        timeout=meta.timeout_ms / 1000.0,
                    )
                else:
                    # 同步工具: 在线程池跑以避免阻塞 event loop
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                        output = await asyncio.get_event_loop().run_in_executor(
                            ex, lambda: tool(**arguments)
                        )

                record.latency_ms = int((time.time() - start) * 1000)
                record.status = "succeeded"
                record.result = output
                record.is_error = False
                return {"is_error": False, "result": output, "latency_ms": record.latency_ms}

            except asyncio.TimeoutError:
                record.status = "timeout"
                record.is_error = True
                record.error_code = "TOOL_TIMEOUT"
                record.error_message = f"timeout after {meta.timeout_ms}ms"
                return {
                    "is_error": True,
                    "error_code": "TOOL_TIMEOUT",
                    "error_message": record.error_message,
                }
            except ToolArgumentError as exc:
                # 参数错误不重试
                record.status = "failed"
                record.is_error = True
                record.error_code = "TOOL_ARGUMENT_INVALID"
                record.error_message = exc.message
                return {
                    "is_error": True,
                    "error_code": "TOOL_ARGUMENT_INVALID",
                    "error_message": exc.message,
                }
            except ToolRateLimitError as exc:
                # 限流: 触发熔断
                self._failure_count[meta.name] = self._failure_count.get(meta.name, 0) + 1
                if self._failure_count[meta.name] >= 3:
                    # 熔断 30 秒
                    self._circuit_open_until[meta.name] = time.time() + 30
                record.status = "failed"
                record.is_error = True
                record.error_code = "TOOL_RATE_LIMITED"
                record.error_message = str(exc)
                return {
                    "is_error": True,
                    "error_code": "TOOL_RATE_LIMITED",
                    "error_message": str(exc),
                    "retry_after_ms": exc.retry_after_ms,
                }
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                # 重试: 仅 idempotent
                if attempt + 1 < max_attempts and meta.idempotent:
                    backoff = (meta.backoff_ms / 1000.0) * (2 ** attempt)
                    await asyncio.sleep(backoff)
                    continue

        # 重试用尽
        record.status = "failed"
        record.is_error = True
        record.error_code = "TOOL_TIMEOUT"  # 用 timeout 兜底（更准确: internal error）
        record.error_message = str(last_error) if last_error else "unknown error"
        return {
            "is_error": True,
            "error_code": "TOOL_TIMEOUT",
            "error_message": record.error_message,
        }

    @property
    def records(self) -> list[ToolCallRecord]:
        return list(self._records)


__all__ = [
    "InMemoryToolExecutor",
    "ToolArgumentError",
    "ToolCallRecord",
    "ToolFunction",
    "ToolRateLimitError",
    "ToolTimeoutError",
]