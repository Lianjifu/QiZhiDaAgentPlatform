"""**结果事件的唯一实现** ✓ —— 一律产出**对外 chunk** ✓（A-39 ✓）。

⚠️ **这里没有第二套事件类型** ✓ —— 之前 ``result/events.py`` 里有 **16 种
``*Event``** ✓（与对外 chunk **一一对应** ✓ —— 两套形状 = 两处要改 ✗✗）→
现在**只剩 chunk** ✓（``qzdap_schema.dtos.turn`` ✓ —— **前端已经认这个**
✓）。

⚠️ **换的过程中不能丢字段** ✓（方案 A-39 的提醒 ✓）—— 内部事件多带的东西
已经**补进 chunk 契约** ✓（``event_id`` ✓ / usage 的 6 维 ✓ / error 的
``detailed`` ✓ / ``source_turn_id`` ✓ / ``query_hash`` ✓ / ``removed_ids``
✓ / ``expires_at`` ✓ / done 的状态与版本 ✓）—— **不是「丢信息换简洁」**
✓（那是数据丢失 ✗✗）。

⚠️ **降级标记的词汇只有三个** ✓（Gateway 方案 §9.0 ✓ —— C-22 ✓）。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal
from uuid import NAMESPACE_OID, UUID, uuid5

from qzdap_kernel.error_codes import ErrorCode
from qzdap_schema.dtos.turn import (
    ApprovalRequiredChunk,
    ArtifactReadyChunk,
    AttachmentReadyChunk,
    ContextCompactedChunk,
    DoneChunk,
    ErrorChunk,
    InteractiveActionChunk,
    KnowledgeSearchChunk,
    MemoryWriteChunk,
    MessageChunk,
    PlanProposedChunk,
    QueuedChunk,
    SkillInvocationChunk,
    ToolCallChunk,
    ToolResultChunk,
    UsageChunk,
    WorkflowInvocationChunk,
)

#: **降级标记** ✓（Gateway 方案 §9.0 ✓ —— 单一来源 ✓）。
DegradationFlag = Literal[
    "recall_degraded",
    "compaction_degraded",
    "interactive_degraded",
]

#: **降级标记的取值集合** ✓（出站只放行这三个 ✓ —— 认不出来的丢掉 ✓）。
DEGRADATION_FLAGS: frozenset[str] = frozenset(
    {"recall_degraded", "compaction_degraded", "interactive_degraded"}
)


def _uuid(value: Any) -> UUID:
    """**字符串 → UUID** ✓ —— 认不出来就**确定性派生** ✓（不是随机 ✓ —— 可复现 ✓）。"""
    try:
        return UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        return uuid5(NAMESPACE_OID, str(value))


def _flags(payload: Mapping[str, Any]) -> list[str]:
    """**取出降级标记** ✓（只放行已知的三个 ✓）。"""
    return [str(flag) for flag in (payload.get("flags") or []) if str(flag) in DEGRADATION_FLAGS]


def to_chunk(
    *,
    event_type: str,
    payload: Mapping[str, Any] | None,
    turn_id: str,
    seq: int,
    event_id: str,
    trace_id: str | None = None,
) -> Any:
    """**一条事件 → 一个对外 chunk** ✓。

    ⚠️ **未知类型落成 ``ErrorChunk``** ✓（不抛 ✓ —— 投递失败要能被 worker
    记成 FAILED ✓ —— 而不是让 worker 自己崩 ✓）。
    """
    data = payload or {}
    common = {
        "turn_id": _uuid(turn_id),
        "seq": int(seq),
        "event_id": event_id,
        "trace_id": trace_id,
        "flags": _flags(data),
    }

    # ⚠️ **IM 的回复** ✓（事件类型是 ``im_reply`` ✓ —— 出站队列里那一条 ✓
    # —— 载荷与 ``message`` **同形** ✓ —— 都是「一段文本」✓）。
    if event_type in ("message", "im_reply"):
        return MessageChunk(
            **common,
            content=str(data.get("content", "") or data.get("text", "") or data.get("delta", "")),
        )
    if event_type == "tool_call":
        return ToolCallChunk(
            **common,
            tool_call_id=_uuid(data.get("tool_call_id")),
            tool_name=str(data.get("tool_name", "")),
            arguments=dict(data.get("arguments") or {}),
        )
    if event_type == "tool_result":
        output = data.get("output")
        return ToolResultChunk(
            **common,
            tool_call_id=_uuid(data.get("tool_call_id")),
            output=output if isinstance(output, (str, dict)) else str(output or ""),
            is_error=bool(data.get("is_error", False)),
            latency_ms=int(data.get("latency_ms", 0)),
        )
    if event_type == "skill_invocation":
        return SkillInvocationChunk(
            **common,
            invocation_id=_uuid(data.get("invocation_id")),
            skill_name=str(data.get("skill", "") or data.get("skill_name", "")),
            status=str(data.get("status", "started")),  # type: ignore[arg-type]
            tool_call_id=_uuid(data["tool_call_id"]) if data.get("tool_call_id") else None,
        )
    if event_type == "memory_write":
        return MemoryWriteChunk(
            **common,
            layer=str(data.get("layer", "l1")),  # type: ignore[arg-type]
            preview=str(data.get("preview", "")),
            source_turn_id=str(data.get("source_turn_id", "")),
        )
    if event_type == "knowledge_search":
        return KnowledgeSearchChunk(
            **common,
            query=str(data.get("query", "") or data.get("query_hash", "")),
            query_hash=str(data.get("query_hash", "")),
            hits=list(data.get("hits") or []),
            citations=list(data.get("citations") or []),
            degraded=bool(data.get("degraded", False)),
        )
    if event_type == "context_compacted":
        return ContextCompactedChunk(
            **common,
            tokens_before=int(data.get("tokens_before", 0)),
            tokens_after=int(data.get("tokens_after", 0)),
            degraded=bool(data.get("degraded", False)),
            removed_ids=[str(item) for item in (data.get("removed_ids") or [])],
        )
    if event_type == "approval_required":
        return ApprovalRequiredChunk(
            **common,
            approval_id=_uuid(data.get("approval_id")),
            tool_name=str(data.get("tool", "") or data.get("tool_name", "")),
            arguments=dict(data.get("arguments") or {})
            or {"preview": str(data.get("args_preview", ""))},
            reason=str(data.get("reason", "")),
            expires_at=str(data.get("expires_at", "")),
        )
    if event_type == "usage":
        return UsageChunk(
            **common,
            input_tokens=int(data.get("input_tokens", 0)),
            output_tokens=int(data.get("output_tokens", 0)),
            cache_read_tokens=int(data.get("cache_read_tokens", data.get("cache_tokens", 0))),
            cache_write_tokens=int(data.get("cache_write_tokens", 0)),
            cost_usd=float(data.get("cost_usd") or 0.0),
            tenant_id=str(data.get("tenant_id", "")),
            workspace_id=str(data.get("workspace_id", "")),
            user_id=str(data.get("user_id", "")),
            agent_id=str(data.get("agent_id", "")),
            agent_version=str(data.get("agent_version", "")),
            model_version=str(data.get("model_version", "")),
            retry_count=int(data.get("retry_count", 0)),
        )
    if event_type == "done":
        return DoneChunk(
            **common,
            final_message=str(data.get("final_message", "") or ""),
            status=str(data.get("status", "succeeded")),  # type: ignore[arg-type]
            agent_version=str(data.get("agent_version", "")),
            model_version=str(data.get("model_version", "")),
        )
    if event_type == "error":
        return _error_chunk(common, data)
    if event_type == "queued":
        return QueuedChunk(
            **common,
            position=int(data.get("position", 0)),
            waited_ms=int(data.get("waited_ms", 0)),
            estimated_wait_seconds=float(data.get("estimated_wait_seconds", 0.0)),
        )
    if event_type == "plan_proposed":
        return PlanProposedChunk(
            **common,
            plan_id=_uuid(data.get("plan_id")),
            title=str(data.get("title", "")),
            steps=list(data.get("steps") or []),
            reason=str(data.get("reason", "")),
        )
    if event_type == "artifact_ready":
        return ArtifactReadyChunk(
            **common,
            artifact_id=_uuid(data.get("artifact_id")),
            kind_=str(data.get("kind_", "text")),  # type: ignore[arg-type]
            name=str(data.get("name", "")),
            mime=str(data.get("mime", "")),
            size_bytes=int(data.get("size_bytes", 0)),
            download_path=str(data.get("download_path", "")),
            preview_path=data.get("preview_path"),
            snippet=str(data.get("snippet", "")),
        )
    if event_type == "attachment_ready":
        return AttachmentReadyChunk(
            **common,
            attachment_id=_uuid(data.get("attachment_id")),
            name=str(data.get("name", "")),
            mime=str(data.get("mime", "")),
            size_bytes=int(data.get("size_bytes", 0)),
            download_path=str(data.get("download_path", "")),
        )
    if event_type == "workflow_invocation":
        return WorkflowInvocationChunk(
            **common,
            invocation_id=_uuid(data.get("invocation_id")),
            workflow_name=str(data.get("workflow_name", "")),
            status=str(data.get("status", "started")),  # type: ignore[arg-type]
        )
    if event_type == "interactive_action":
        return InteractiveActionChunk(
            **common,
            call_id=str(data.get("call_id", "")),
            action=str(data.get("action", "toast")),  # type: ignore[arg-type]
            payload=dict(data.get("payload") or {}),
        )
    return ErrorChunk(
        **common,
        code=ErrorCode.INTERNAL_ERROR.value,
        message="未知事件类型",
        detailed=f"unknown event type: {event_type}",
    )


def _error_chunk(common: dict[str, Any], data: Mapping[str, Any]) -> ErrorChunk:
    """**错误块** ✓（旧事件用 ``error_code`` / ``safe_message`` ✓ —— 新的用
    ``code`` / ``message`` ✓ —— 两个都认 ✓ —— 别丢数据 ✗✗）。"""
    return ErrorChunk(
        **common,
        code=str(data.get("code") or data.get("error_code") or "INTERNAL_ERROR"),
        message=str(data.get("message") or data.get("safe_message") or ""),
        retriable=bool(data.get("retriable", False)),
        detailed=data.get("detailed"),
    )


__all__ = [
    "DEGRADATION_FLAGS",
    "DegradationFlag",
    "to_chunk",
]
