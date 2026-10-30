"""**重试与熔断** ✓（Agent 方案 §5.3.3 ✓）。

| # | 能力 | 规则 |
|---|---|---|
| 1 | 重试 | 指数退避 + jitter ✓，**仅对幂等工具的瞬时错误** ✓ |
| 2 | 熔断 | 按**工具名**计连续失败 ✓ → 熔断若干秒 ✓ → `TOOL_RATE_LIMITED` ✓ |
| 3 | 幂等命中 | **不重试** ✓（直接返回既有结果 ✓） |
| 4 | 参数错误 | **不重试** ✓（`TOOL_ARGUMENT_INVALID` ✓） |

⚠️ **熔断状态是进程内的** ✓ —— 跨 worker 的共享熔断需要共享存储 ✓（那是
后话 ✗ —— **进程内熔断已经能挡住「一个工具持续打不通还在被反复调」** ✓）。
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field

#: **瞬时错误** ✓（值得重试 ✓）—— 超时 ✓ / 连接错误 ✓ / 上游 5xx ✓。
#: ⚠️ **参数错误不在里面** ✓（重试它只是把同一个错误重复一遍 ✗✗）。
_TRANSIENT_NAMES = (
    "TimeoutError",
    "ConnectError",
    "ConnectTimeout",
    "ReadTimeout",
    "WriteTimeout",
    "PoolTimeout",
    "RemoteProtocolError",
    "ToolCallTimeout",
)


def is_transient(exc: BaseException) -> bool:
    """**这个错误值得重试吗** ✓（瞬时 ✓）。"""
    return type(exc).__name__ in _TRANSIENT_NAMES


def retry_delay_ms(
    attempt: int,
    *,
    base_ms: int = 200,
    max_ms: int = 5_000,
    jitter: float = 0.2,
    rand: random.Random | None = None,
) -> int:
    """**第 ``attempt`` 次失败后等多久** ✓（指数退避 ✓ + jitter ✓）。

    ⚠️ **jitter 是必需的** ✓ —— 固定退避会让一批调用**同时**重试 ✗✗
    （惊群 ✓ —— 那正是熔断要防的事 ✓）。
    """
    exponent = max(0, attempt - 1)
    base = min(max_ms, base_ms * (2**exponent))
    source = rand or random
    spread = base * jitter
    return int(max(0, base - spread + source.random() * spread * 2))


@dataclass(slots=True)
class CircuitBreaker:
    """**按工具名计的熔断器** ✓（连续失败达阈值就熔断 ✓）。

    ⚠️ **半开**：熔断期满后放**一次**探测 ✓ —— 成功就复位 ✓，失败就继续
    熔断 ✓（不然一次偶发成功就放洪水 ✗✗）。
    """

    threshold: int = 5
    cooldown_seconds: float = 30.0
    _failures: dict[str, int] = field(default_factory=dict)
    _opened_at: dict[str, float] = field(default_factory=dict)
    _probing: set[str] = field(default_factory=set)

    def is_open(self, tool_name: str, *, now: float | None = None) -> bool:
        """**这个工具现在被熔断了吗** ✓。"""
        opened_at = self._opened_at.get(tool_name)
        if opened_at is None:
            return False
        current = time.monotonic() if now is None else now
        if current - opened_at >= self.cooldown_seconds:
            # ⚠️ **半开** ✓ —— 放一次探测 ✓
            if tool_name not in self._probing:
                self._probing.add(tool_name)
                return False
            return True
        return True

    def retry_after_ms(self, tool_name: str, *, now: float | None = None) -> int:
        """**还要等多久才能再试** ✓（毫秒 ✓）。"""
        opened_at = self._opened_at.get(tool_name)
        if opened_at is None:
            return 0
        current = time.monotonic() if now is None else now
        remaining = self.cooldown_seconds - (current - opened_at)
        return int(max(0, remaining) * 1000)

    def record_success(self, tool_name: str) -> None:
        """**成功** ✓ —— 计数清零 ✓ + 熔断解除 ✓。"""
        self._failures.pop(tool_name, None)
        self._opened_at.pop(tool_name, None)
        self._probing.discard(tool_name)

    def record_failure(self, tool_name: str, *, now: float | None = None) -> None:
        """**失败** ✓ —— 计数 +1 ✓；到阈值就熔断 ✓。"""
        current = time.monotonic() if now is None else now
        count = self._failures.get(tool_name, 0) + 1
        self._failures[tool_name] = count
        if count >= self.threshold:
            self._opened_at[tool_name] = current
            self._probing.discard(tool_name)

    def failures(self, tool_name: str) -> int:
        """**连续失败次数** ✓（给指标 / 测试看 ✓）。"""
        return self._failures.get(tool_name, 0)


__all__ = ["CircuitBreaker", "is_transient", "retry_delay_ms"]
