"""Memory 协议层：§13.4 LayeredMemory + InMemoryLayeredMemory + 召回流水线。

Stage 3 PR A 范围：L1 (消息/摘要) + L2 (事实) + L3 (知识) + 召回流水线。
Stage 3 PR D 范围：remember 节点 + memory_l2_embeddings 表 + L2 去重/提升。
"""

from __future__ import annotations

import asyncio
import concurrent.futures
from typing import Any

from .layered import (
    InMemoryLayeredMemory,
    L1Source,
    L2Fact,
    L3Chunk,
)


def run_async_from_sync(coro: Any) -> Any:
    """从同步上下文运行 coroutine (处理已有的 event loop)。

    节点函数是同步的, 但 InMemoryLayeredMemory 的 Protocol 方法是 async。
    本辅助检测当前 loop: 没有则 asyncio.run, 已有则用 ThreadPoolExecutor。
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        return ex.submit(asyncio.run, coro).result()


__all__ = [
    "InMemoryLayeredMemory",
    "L1Source",
    "L2Fact",
    "L3Chunk",
    "run_async_from_sync",
]