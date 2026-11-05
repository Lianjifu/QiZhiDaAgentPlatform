"""**LLM 上游重试** ✓ —— 指数退避 + jitter ✓。

⚠️ **只重试「瞬时」失败** ✓ —— 参数错 / 鉴权错 / 内容过滤**重试也没用** ✗✗
（重试只是把同一个错再犯一遍 ✓ + 拖慢首字延迟 ✗✗）。

| 失败 | 重试 | 理由 |
|---|---|---|
| 连接错 / 超时 | ✓ | 上游可能只是抖了一下 |
| 429 限流 | ✓ | 有配额窗口 ✓ |
| 5xx | ✓ | 上游内部错误 |
| 400 / 401 / 403 / 404 | ✗ | 请求本身有问题 ✓ |
| 已经开始流式输出后的中断 | ✗ | 重放会**重复吐字** ✗✗ |

⚠️ **流式只重试「还没吐出第一个 chunk」的那一段** ✓ —— 这是本模块最要紧
的一条边界 ✓（否则用户会看到同一句话出现两遍 ✗✗）。
"""

from __future__ import annotations

import random
from dataclasses import dataclass

import httpx

#: **值得重试的状态码** ✓ —— 限流 ✓ + 请求超时 ✓ + 上游 5xx ✓。
_RETRYABLE_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504, 529})

#: **值得重试的异常类型** ✓ —— 连接层 ✓ + 读超时 ✓ + 远端协议错 ✓。
_RETRYABLE_EXCEPTIONS = (
    httpx.TimeoutException,
    httpx.ConnectError,
    httpx.NetworkError,
    httpx.RemoteProtocolError,
)


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """**重试策略** ✓ —— 次数 ✓ / 退避基数 ✓ / 上限 ✓ / 抖动 ✓。

    ⚠️ ``max_attempts=1`` = **不重试** ✓（默认值给 3 次 ✓ —— 首次 + 两次重试
    ✓ —— 只重试瞬时错误 ✓）。
    """

    max_attempts: int = 3
    base_delay_seconds: float = 0.2
    max_delay_seconds: float = 5.0
    jitter: float = 0.2

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        if self.base_delay_seconds < 0:
            raise ValueError("base_delay_seconds must be >= 0")
        if self.max_delay_seconds < 0:
            raise ValueError("max_delay_seconds must be >= 0")
        if not 0 <= self.jitter <= 1:
            raise ValueError("jitter must be within [0, 1]")

    def delay_seconds(self, attempt: int, *, rand: random.Random | None = None) -> float:
        """**第 ``attempt`` 次失败后等多久** ✓（指数退避 ✓ + jitter ✓）。

        ⚠️ **jitter 是必需的** ✓ —— 固定退避会让一批请求**同时**重试 ✗✗
        （惊群 ✓ —— 上游刚恢复就会被我们自己打死 ✗✗）。
        """
        exponent = max(0, attempt - 1)
        base = min(self.max_delay_seconds, self.base_delay_seconds * (2**exponent))
        source = rand or random
        spread = base * self.jitter
        return max(0.0, base - spread + source.random() * spread * 2)

    def should_retry_status(self, status_code: int) -> bool:
        """**这个状态码值得重试吗** ✓。"""
        return status_code in _RETRYABLE_STATUS or 500 <= status_code < 600

    def should_retry_exception(self, exc: BaseException) -> bool:
        """**这个异常值得重试吗** ✓。"""
        return isinstance(exc, _RETRYABLE_EXCEPTIONS)


def retry_after_seconds(headers: httpx.Headers | None) -> float | None:
    """**上游说了「等多久再试」吗** ✓ —— 读 ``Retry-After`` ✓。

    ⚠️ 只认**秒数** ✓ —— HTTP-date 形式不认 ✗（解析要时区 ✓ + 收益极低 ✗✗）。
    """
    if headers is None:
        return None
    raw = headers.get("retry-after")
    if not raw:
        return None
    try:
        seconds = float(raw.strip())
    except ValueError:
        return None
    return seconds if seconds >= 0 else None


__all__ = ["RetryPolicy", "retry_after_seconds"]
