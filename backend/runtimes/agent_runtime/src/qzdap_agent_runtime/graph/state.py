"""`SessionState` TypedDict — 19 节点 LangGraph StateGraph 状态契约。

字段命名严格对齐 §2.5 阻塞 3 权威命名表的 19 个节点:

 1.  normalize_input
 2.  acquire_turn_lock
 3.  load_checkpoint
 4.  write_turn_record
 5.  load_agent_context
 6.  recall_memory_and_knowledge
 7.  assemble_context
 8.  compact_if_needed
 9.  route
10.  agent
11.  governance           # agent loop 内
12.  execute              # agent loop 内
13.  deep_agent_plan      # 仅 deep_task=true
14.  subagent             # 仅 deep_task=true
15.  remember
16.  persist_result
17.  emit_result
18.  compact_tool_result
19.  release_turn_lock

§4.1 规定使用 `add_messages` reducer 维护消息；其他字段均不可变更新。
schema_version 在 load_checkpoint 节点同步到当前 state；revision 与
agent_sessions.current_revision 在 acquire_turn_lock 校验。
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


# ---------------------------------------------------------------------------
# 当前 schema 版本；任何节点写入 state 都必须先比较 schema_version。
# 升级时 bump 此常量，并在 load_checkpoint 节点做迁移。
# ---------------------------------------------------------------------------

SCHEMA_VERSION = 1


# ---------------------------------------------------------------------------
# 子类型
# ---------------------------------------------------------------------------


DegradedFlag = Literal[
    "recall_degraded",
    "compaction_degraded",
    "langsmith_degraded",
    "cost_attribution_degraded",
]


class Route(TypedDict, total=False):
    """`route` 节点的输出：路由决策。"""

    deep_task: bool
    task_kind: str  # TaskKind 枚举的字面值
    rule_version: str
    classifier: str  # "heuristic" | "model" | "agent.deep_research"
    confidence: float
    candidates: list[str]
    reason: str


class ToolCallState(TypedDict, total=False):
    """tool_call 追踪状态（governance / execute / remember 三节点共享）。"""

    tool_call_id: str
    tool_name: str
    arguments: dict[str, Any]
    risk: str  # "low" | "medium" | "high"
    status: str  # "pending" | "approved" | "denied" | "running" | "succeeded" | "failed" | "timeout"
    result_ref: str | None  # tool_executions.idempotency_key 或对象存储 pointer
    latency_ms: int
    retry_count: int


class ToolResultState(TypedDict, total=False):
    """execute 节点产出的 tool 结果；compact_tool_result 节点按 >64KB 切片。"""

    tool_call_id: str
    content: str | dict[str, Any]
    is_error: bool
    raw_size_bytes: int
    pointer: str | None  # >64KB 时指向对象存储


class PendingApproval(TypedDict, total=False):
    """governance 节点产出；interrupt 期间持久化在 checkpoint。"""

    approval_id: str
    tool_call_id: str
    tool_name: str
    arguments_hash: str
    policy_id: str
    requester: str  # actor_id
    requested_at: str  # ISO-8601
    expires_at: str  # ISO-8601


class Todo(TypedDict, total=False):
    """deep_agent_plan 节点的 plan/todos 表面化。"""

    id: str
    status: str  # "pending" | "in_progress" | "done" | "skipped"
    content: str
    assigned_subagent: str | None


class ResultState(TypedDict, total=False):
    """最终结果状态；persist_result 节点写入 session_events。"""

    final_message: str
    status: str  # "succeeded" | "failed" | "cancelled"
    error_code: str | None  # ErrorCode 枚举字面值
    agent_version: str
    model_version: str


class UsageState(TypedDict, total=False):
    """cost / token 累计；done 节点汇总 emit usage chunk。"""

    input_tokens: int
    output_tokens: int
    cache_tokens: int
    cost_usd: float | None
    cost_unknown: bool
    attribution_status: str  # "ok" | "degraded"


class RuntimeErrorState(TypedDict, total=False):
    """任意节点抛错时记录的运行时错误；不抛穿图，写入 state.errors 后继续。"""

    node: str  # 节点 ID 或名称
    error_code: str  # ErrorCode 字面值
    message: str
    trace_id: str | None
    retriable: bool
    occurred_at: str  # ISO-8601


# ---------------------------------------------------------------------------
# 主体：SessionState TypedDict
# ---------------------------------------------------------------------------


class SessionState(TypedDict, total=False):
    """会话 turn 完整运行时状态。

    节点写入此 TypedDict；reducer 仅作用于 `messages` 字段。其他字段由
    对应节点直接覆盖或 None-init。
    """

    # ---- 标识与会话元数据 ----
    schema_version: int
    tenant_id: str
    workspace_id: str
    session_id: str
    turn_id: str
    thread_id: str  # 与 session_id 一致
    idempotency_key: str

    # ---- 修订与版本 ----
    revision: int  # state-level checkpoint revision
    expected_revision: int | None  # acquire_turn_lock 校验用
    trace_id: str
    agent_id: str
    agent_version: str  # 冻结到 turn 开始
    model_version: str  # 冻结到 turn 开始

    # ---- 消息 / 摘要 / 上下文 ----
    messages: Annotated[list[Any], add_messages]
    rolling_summary: str
    context_manifest: dict[str, Any]

    # ---- 记忆与召回 ----
    memory_hits: list[dict[str, Any]]  # L1+L2 RecallHit
    knowledge_hits: list[dict[str, Any]]  # L3 RecallHit

    # ---- 路由与工具调用 ----
    route: Route
    pending_approval: PendingApproval | None
    tool_calls: list[ToolCallState]
    tool_results: list[ToolResultState]
    todos: list[Todo]

    # ---- 结果 / 用量 / 错误 ----
    result: ResultState | None
    usage: UsageState
    emitted_seq: int
    errors: list[RuntimeErrorState]

    # ---- 降级标志（观测层写入） ----
    degraded: dict[str, bool]


__all__ = [
    "DegradedFlag",
    "PendingApproval",
    "ResultState",
    "Route",
    "RuntimeErrorState",
    "SCHEMA_VERSION",
    "SessionState",
    "Todo",
    "ToolCallState",
    "ToolResultState",
    "UsageState",
]