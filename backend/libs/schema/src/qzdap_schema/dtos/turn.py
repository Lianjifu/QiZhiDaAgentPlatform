"""Turn stream chunk DTOs.

The agent_runtime streams turn progress over SSE as a sequence of
`TurnChunk` envelopes. Each chunk carries a `kind` field that the client uses
to dispatch rendering.
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

ChunkKind = Literal[
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
    # Round-7 增量: 计划 / 产物 / 附件 / 工作流
    "plan_proposed",
    "artifact_ready",
    "attachment_ready",
    "workflow_invocation",
    # 前端交互动作 (对应 5 个 stub tool: ask_user_question / notify_user /
    # plan_submit / todo_write / delegate_to_agent). backend 在 tool_result
    # emit 时若 output 含 _pending_frontend_action, 同时发一个
    # interactive_action chunk, payload 透传 result.
    "interactive_action",
]


class ChunkEnvelope(BaseModel):
    """Wrapper around every chunk with shared metadata."""

    model_config = {"populate_by_name": True}

    turn_id: UUID
    seq: int = Field(ge=0)
    kind: ChunkKind


class MessageChunk(ChunkEnvelope):
    kind: Literal["message"] = "message"
    content: str
    role: Literal["assistant"] = "assistant"


class ToolCallChunk(ChunkEnvelope):
    kind: Literal["tool_call"] = "tool_call"
    tool_call_id: UUID
    tool_name: str
    arguments: dict


class ToolResultChunk(ChunkEnvelope):
    kind: Literal["tool_result"] = "tool_result"
    tool_call_id: UUID
    output: str | dict
    is_error: bool = False
    latency_ms: int = Field(ge=0)


class SkillInvocationChunk(ChunkEnvelope):
    kind: Literal["skill_invocation"] = "skill_invocation"
    invocation_id: UUID
    skill_name: str
    status: Literal["started", "stream", "succeeded", "failed", "cancelled"]


class MemoryWriteChunk(ChunkEnvelope):
    kind: Literal["memory_write"] = "memory_write"
    layer: Literal["l1", "l2"] = "l1"
    preview: str = ""


class ApprovalRequiredChunk(ChunkEnvelope):
    kind: Literal["approval_required"] = "approval_required"
    approval_id: UUID
    tool_name: str
    arguments: dict = Field(default_factory=dict)
    reason: str = ""


class ContextCompactedChunk(ChunkEnvelope):
    kind: Literal["context_compacted"] = "context_compacted"
    tokens_before: int = Field(ge=0, default=0)
    tokens_after: int = Field(ge=0, default=0)


class UsageChunk(ChunkEnvelope):
    kind: Literal["usage"] = "usage"
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    cache_read_tokens: int = Field(ge=0)
    cache_write_tokens: int = Field(ge=0)
    cost_usd: float = Field(ge=0)


class DoneChunk(ChunkEnvelope):
    kind: Literal["done"] = "done"
    final_message: str | None = None


class ErrorChunk(ChunkEnvelope):
    kind: Literal["error"] = "error"
    code: str
    message: str
    retriable: bool = False


# ---------------------------------------------------------------------------
# Round-7 增量: 计划 / 产物 / 附件 / 工作流 (与 ResultEvent 一一对应)
# ---------------------------------------------------------------------------


class PlanProposedChunk(ChunkEnvelope):
    """模型提议的待执行计划; 前端用作 plan card (按步批准 / 拒绝)."""

    kind: Literal["plan_proposed"] = "plan_proposed"
    plan_id: UUID
    title: str
    steps: list[dict] = Field(
        default_factory=list,
        description="每步 {id, title, description, kind: tool|subagent|ask, tool_name?}",
    )
    reason: str = ""


class ArtifactReadyChunk(ChunkEnvelope):
    """工具 / 模型生成了可下载的产物 (报告 / 代码 / html / json)."""

    kind: Literal["artifact_ready"] = "artifact_ready"
    artifact_id: UUID
    kind_: Literal["markdown", "code", "html", "json", "image", "text"] = Field(
        alias="kind",
        description="产物类别 (字段名 kind 与 envelope 重复, 用 alias 暴露为 kind_)",
    )
    name: str
    mime: str
    size_bytes: int = Field(ge=0)
    download_path: str = Field(
        description="相对路径 e.g. /api/sessions/{sid}/artifacts/{aid}/content",
    )
    preview_path: str | None = None
    snippet: str = Field(default="", description="前 800 字预览; markdown 渲染用")


class AttachmentReadyChunk(ChunkEnvelope):
    """用户附件已就绪 (上传完成 / 解析完成)."""

    kind: Literal["attachment_ready"] = "attachment_ready"
    attachment_id: UUID
    name: str
    mime: str
    size_bytes: int = Field(ge=0)
    download_path: str


class WorkflowInvocationChunk(ChunkEnvelope):
    """工作流调用状态 (类似 skill_invocation, 但目标是一个工作流)."""

    kind: Literal["workflow_invocation"] = "workflow_invocation"
    invocation_id: UUID
    workflow_name: str
    status: Literal["started", "succeeded", "failed", "cancelled"]


class InteractiveActionChunk(ChunkEnvelope):
    """Stub tool (ask_user_question / notify_user / plan_submit /
    todo_write / delegate_to_agent) 完成后, backend 在 tool_result
    chunk 之后再发一个这个 chunk. 前端用它分派 UI (modal/toast/drawer/router).
    """

    kind: Literal["interactive_action"] = "interactive_action"
    call_id: str
    action: Literal["show_question_card", "toast", "render_plan",
                   "render_todo_list", "delegate_agent"]
    payload: dict = Field(default_factory=dict)


class KnowledgeSearchChunk(ChunkEnvelope):
    """知识检索结果 (hit 摘要 + 引用 + 降级标记)."""

    kind: Literal["knowledge_search"] = "knowledge_search"
    query: str
    hits: list[dict] = Field(
        default_factory=list,
        description="每条 {id, title, snippet, score}",
    )
    citations: list[str] = Field(default_factory=list)
    degraded: bool = False


# Type union for client-side discriminated parsing
TurnChunk = (
    MessageChunk
    | ToolCallChunk
    | ToolResultChunk
    | SkillInvocationChunk
    | MemoryWriteChunk
    | KnowledgeSearchChunk
    | ApprovalRequiredChunk
    | ContextCompactedChunk
    | UsageChunk
    | DoneChunk
    | ErrorChunk
    | PlanProposedChunk
    | ArtifactReadyChunk
    | AttachmentReadyChunk
    | WorkflowInvocationChunk
    | InteractiveActionChunk
)
