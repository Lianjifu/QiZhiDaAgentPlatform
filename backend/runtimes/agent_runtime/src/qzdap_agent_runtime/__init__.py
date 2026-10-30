"""qzdap_agent_runtime —— 契约层 ✓（Gateway ✓ / Router ✓ / Session ✓ / Context ✓ / Memory ✓ / Agent Loop ✓）。

⚠️ **这里是「契约」不是「实现」** ✓ —— 端口 ✓ / DTO ✓ / 判定点 ✓；
**真实实现**归各模块 ✓（``modules/*`` ✓）—— 契约层**不认识**任何具体实现 ✓。

⚠️ **2026-10-31（Agent Stage 7）** ✓ —— **未接线的整包清掉了** ✓：
19 节点图 ✓ / 13 个空壳节点 ✓ / 16 个 ``InMemory*`` 假实现 ✓ /
占位图 ✓ / ``budget.py`` ✓ / ``layered.py`` ✓ —— **生产包零 ``InMemory*``** ✓
（架构守卫 `tests/architecture/test_single_implementation.py` ✓ 在盯 ✓）。
"""

from __future__ import annotations

from . import (
    agent_loop,
    agent_router,
    channels,
    context,
    execution,
    gateway,
    memory,
    outbox,
    ports,
    result,
    router,
    session,
)

__all__ = [
    "agent_loop",
    "agent_router",
    "channels",
    "context",
    "execution",
    "gateway",
    "memory",
    "outbox",
    "ports",
    "result",
    "router",
    "session",
]
