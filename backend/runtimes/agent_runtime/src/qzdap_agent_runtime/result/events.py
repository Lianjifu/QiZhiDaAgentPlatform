"""Result event types — runtime 内部协议 (§13.5)。

ResultEvent 是 runtime 内部事件协议，与 `qzdap_schema.dtos.turn.TurnChunk`
对外 chunk 是单一适配器关系（§13.5）。每个事件携带 `turn_id`、单调 `seq`、
`event_id`、`trace_id` 和 `retriable`。SSE 使用 `id: seq` 协议。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Event kind 字面值：与 §13.5 表格"对外 chunk"列一一对应
# ---------------------------------------------------------------------------


EventKind = Literal[
    "message",
    "tool_call",
    "tool_result",
    "skill_invocation",
    "memory_write",
    "knowledge_search",
    "approval_required",
    "context_compacted",
    "usage",
    "done",
    "error",
    # Round-7 增量
    "plan_proposed",
    "artifact_ready",
    "attachment_ready",
    "workflow_invocation",
]


# ---------------------------------------------------------------------------
# 公共字段
# ---------------------------------------------------------------------------


class _EventBase(BaseModel):
    """所有 ResultEvent 的公共字段。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    turn_id: str
    seq: int = Field(ge=0)
    event_id: str
    trace_id: str | None = None
    retriable: bool = False


# ---------------------------------------------------------------------------
# 11 种 event 类型
# ---------------------------------------------------------------------------


class MessageEvent(_EventBase):
    """agent 节点的 on_chat_model_stream → message chunk。"""

    kind: Literal["message"] = "message"
    delta: str
    role: Literal["assistant", "system"] = "assistant"


class ToolCallEvent(_EventBase):
    """execute 节点的 on_tool_start → tool_call chunk。"""

    kind: Literal["tool_call"] = "tool_call"
    tool_name: str
    tool_call_id: str
    arguments: dict


class ToolResultEvent(_EventBase):
    """execute 节点的 on_tool_end → tool_result chunk。"""

    kind: Literal["tool_result"] = "tool_result"
    tool_call_id: str
    output: object
    is_error: bool
    latency_ms: int


class SkillInvocationEvent(_EventBase):
    """execute 节点的 skill_invocation custom event。"""

    kind: Literal["skill_invocation"] = "skill_invocation"
    invocation_id: str
    skill: str
    status: Literal["started", "succeeded", "failed", "timeout"]


class MemoryWriteEvent(_EventBase):
    """remember 节点的 memory_write custom event。"""

    kind: Literal["memory_write"] = "memory_write"
    layer: Literal["l1", "l2"]
    source_turn_id: str
    preview: str


class KnowledgeSearchEvent(_EventBase):
    """recall_memory_and_knowledge 节点的 knowledge_search custom event。"""

    kind: Literal["knowledge_search"] = "knowledge_search"
    query_hash: str
    hits: list[dict]
    citations: list[str]
    degraded: bool


class ContextCompactedEvent(_EventBase):
    """compact_if_needed / compact_tool_result 节点的 context_compacted custom event。"""

    kind: Literal["context_compacted"] = "context_compacted"
    tokens_before: int
    tokens_after: int
    removed_ids: list[str]


class ApprovalRequiredEvent(_EventBase):
    """governance 节点的 interrupt → approval_required chunk。"""

    kind: Literal["approval_required"] = "approval_required"
    approval_id: str
    tool_call_id: str
    tool: str
    args_preview: str
    reason: str
    expires_at: str  # ISO-8601
    retriable: Literal[False] = False  # 审批无法通过重试解决


class UsageEvent(_EventBase):
    """done 节点的 usage custom event（§5.10）。"""

    kind: Literal["usage"] = "usage"
    input_tokens: int
    output_tokens: int
    cache_tokens: int
    cost_usd: float | None
    cost_unknown: bool
    tenant_id: str
    workspace_id: str
    user_id: str
    agent_id: str
    agent_version: str
    model_version: str
    retry_count: int


class DoneEvent(_EventBase):
    """done 节点产出 DoneChunk (§13.5)。"""

    kind: Literal["done"] = "done"
    final_message: str
    status: Literal["succeeded", "failed", "cancelled"]
    agent_version: str
    model_version: str


class ErrorEvent(_EventBase):
    """任意节点抛错时产出 error chunk。"""

    kind: Literal["error"] = "error"
    error_code: str  # ErrorCode 枚举字面值
    safe_message: str  # 给用户看的安全摘要
    detailed: str | None = None  # 仅日志/trace 用


# ---------------------------------------------------------------------------
# Round-7 增量: 计划 / 产物 / 附件 / 工作流
# ---------------------------------------------------------------------------


class PlanProposedEvent(_EventBase):
    """模型提议计划 (前端用作可批准/拒绝的步骤卡片)."""

    kind: Literal["plan_proposed"] = "plan_proposed"
    plan_id: str
    title: str
    steps: list[dict]
    reason: str = ""


class ArtifactReadyEvent(_EventBase):
    """工具/模型产出可下载产物 (报告/代码/html/json)."""

    kind: Literal["artifact_ready"] = "artifact_ready"
    artifact_id: str
    kind_: Literal["markdown", "code", "html", "json", "image", "text"]
    name: str
    mime: str
    size_bytes: int
    download_path: str
    preview_path: str | None = None
    snippet: str = ""


class AttachmentReadyEvent(_EventBase):
    """用户附件就绪 (上传完成 / 解析完成)."""

    kind: Literal["attachment_ready"] = "attachment_ready"
    attachment_id: str
    name: str
    mime: str
    size_bytes: int
    download_path: str


class WorkflowInvocationEvent(_EventBase):
    """工作流调用状态 (类似 skill_invocation)."""

    kind: Literal["workflow_invocation"] = "workflow_invocation"
    invocation_id: str
    workflow_name: str
    status: Literal["started", "succeeded", "failed", "cancelled"]


# ---------------------------------------------------------------------------
# ResultEvent 联合类型（discriminated by kind）
# ---------------------------------------------------------------------------


ResultEvent = (
    MessageEvent
    | ToolCallEvent
    | ToolResultEvent
    | SkillInvocationEvent
    | MemoryWriteEvent
    | KnowledgeSearchEvent
    | ContextCompactedEvent
    | ApprovalRequiredEvent
    | UsageEvent
    | DoneEvent
    | ErrorEvent
    | PlanProposedEvent
    | ArtifactReadyEvent
    | AttachmentReadyEvent
    | WorkflowInvocationEvent
)


__all__ = [
    "ApprovalRequiredEvent",
    "ArtifactReadyEvent",
    "AttachmentReadyEvent",
    "ContextCompactedEvent",
    "DoneEvent",
    "ErrorEvent",
    "EventKind",
    "KnowledgeSearchEvent",
    "MemoryWriteEvent",
    "MessageEvent",
    "PlanProposedEvent",
    "ResultEvent",
    "SkillInvocationEvent",
    "ToolCallEvent",
    "ToolResultEvent",
    "UsageEvent",
    "WorkflowInvocationEvent",
]