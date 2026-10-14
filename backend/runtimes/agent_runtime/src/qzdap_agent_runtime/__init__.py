"""qzdap_agent_runtime — LangGraph-based agent runtime library.

见 docs/refactor/session-module-refactor-plan.md §3.1 / §7.2。

Stage 1 + Stage 2 PR A/B/C/D 范围内交付：

- `graph.SessionState` TypedDict（19 节点字段对齐）
- `graph.build_session_graph()` 纯内存 fake 图
- `graph.routing.classify_task_kind_heuristic` (§2.5 阻塞 6)
- `result.events.ResultEvent` 11 种事件类型（§13.5）
- `channels.gateway.ChannelMessage` 入站规范化 DTO（§5.1）
- `ports` 协议：ToolRegistry / LayeredMemory / PolicyGuard / ToolExecutor（§13.3/§13.4/§5.7/§5.8）
- `execution.lock` LockManager + InMemoryLockManager（§4.2/§4.3）
- `outbox` OutboxWorker + InMemoryOutboxRepository（§4.4）
- `graph.from_url` Postgres checkpointer 工厂（§13.1/§14.1）
"""

from __future__ import annotations

from . import channels, execution, graph, memory, outbox, ports, result, tools

__all__ = [
    "channels",
    "execution",
    "graph",
    "memory",
    "outbox",
    "ports",
    "result",
    "tools",
]