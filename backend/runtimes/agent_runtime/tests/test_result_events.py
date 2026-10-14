"""Tests for ResultEvent 11 种类型（§13.5）。"""

from __future__ import annotations

from qzdap_agent_runtime.result import (
    ApprovalRequiredEvent,
    ContextCompactedEvent,
    DoneEvent,
    ErrorEvent,
    KnowledgeSearchEvent,
    MemoryWriteEvent,
    MessageEvent,
    ResultEvent,
    SkillInvocationEvent,
    ToolCallEvent,
    ToolResultEvent,
    UsageEvent,
)


# ---------------------------------------------------------------------------
# 11 种 event 构造 + kind 字面值
# ---------------------------------------------------------------------------


class TestElevenEventKinds:
    def test_message_event(self) -> None:
        e = MessageEvent(
            turn_id="t-1", seq=1, event_id="e-1", delta="hi", role="assistant"
        )
        assert e.kind == "message"
        assert e.retriable is False  # _EventBase 默认

    def test_tool_call_event(self) -> None:
        e = ToolCallEvent(
            turn_id="t-1",
            seq=2,
            event_id="e-2",
            tool_name="search_kb",
            tool_call_id="tc-1",
            arguments={"q": "test"},
        )
        assert e.kind == "tool_call"

    def test_tool_result_event(self) -> None:
        e = ToolResultEvent(
            turn_id="t-1",
            seq=3,
            event_id="e-3",
            tool_call_id="tc-1",
            output={"hits": []},
            is_error=False,
            latency_ms=120,
        )
        assert e.kind == "tool_result"
        assert e.latency_ms == 120

    def test_skill_invocation_event(self) -> None:
        e = SkillInvocationEvent(
            turn_id="t-1",
            seq=4,
            event_id="e-4",
            invocation_id="inv-1",
            skill="pdf-summarize",
            status="started",
        )
        assert e.kind == "skill_invocation"

    def test_memory_write_event(self) -> None:
        e = MemoryWriteEvent(
            turn_id="t-1",
            seq=5,
            event_id="e-5",
            layer="l2",
            source_turn_id="t-0",
            preview="user prefers Chinese",
        )
        assert e.kind == "memory_write"
        assert e.layer == "l2"

    def test_knowledge_search_event(self) -> None:
        e = KnowledgeSearchEvent(
            turn_id="t-1",
            seq=6,
            event_id="e-6",
            query_hash="hash-x",
            hits=[{"id": "k-1"}],
            citations=["doc://k-1"],
            degraded=False,
        )
        assert e.kind == "knowledge_search"

    def test_context_compacted_event(self) -> None:
        e = ContextCompactedEvent(
            turn_id="t-1",
            seq=7,
            event_id="e-7",
            tokens_before=20_000,
            tokens_after=8_000,
            removed_ids=["m-1", "m-2"],
        )
        assert e.kind == "context_compacted"
        assert e.tokens_after < e.tokens_before

    def test_approval_required_event(self) -> None:
        e = ApprovalRequiredEvent(
            turn_id="t-1",
            seq=8,
            event_id="e-8",
            approval_id="apr-1",
            tool_call_id="tc-2",
            tool="send_email",
            args_preview="to: x@y",
            reason="pii outbound",
            expires_at="2026-10-15T10:15:00Z",
        )
        assert e.kind == "approval_required"
        # ApprovalRequiredEvent 强制 retriable=False
        assert e.retriable is False

    def test_usage_event(self) -> None:
        e = UsageEvent(
            turn_id="t-1",
            seq=9,
            event_id="e-9",
            input_tokens=1200,
            output_tokens=800,
            cache_tokens=200,
            cost_usd=0.05,
            cost_unknown=False,
            tenant_id="tnt-1",
            workspace_id="ws-1",
            user_id="u-1",
            agent_id="agt-1",
            agent_version="v1.0",
            model_version="gpt-5-2025-01",
            retry_count=0,
        )
        assert e.kind == "usage"
        # usage event 必须携带完整维度（§5.10）
        for required in (
            "tenant_id",
            "workspace_id",
            "user_id",
            "agent_id",
            "agent_version",
            "model_version",
        ):
            assert getattr(e, required), f"missing {required}"

    def test_done_event(self) -> None:
        e = DoneEvent(
            turn_id="t-1",
            seq=10,
            event_id="e-10",
            final_message="completed",
            status="succeeded",
            agent_version="v1.0",
            model_version="gpt-5-2025-01",
        )
        assert e.kind == "done"
        assert e.status == "succeeded"

    def test_error_event(self) -> None:
        e = ErrorEvent(
            turn_id="t-1",
            seq=11,
            event_id="e-11",
            error_code="TOOL_TIMEOUT",
            safe_message="工具执行超时，请稍后重试",
            detailed="full traceback ...",
            retriable=True,
        )
        assert e.kind == "error"
        assert e.retriable is True


# ---------------------------------------------------------------------------
# 联合类型
# ---------------------------------------------------------------------------


def test_result_event_union_includes_all_11() -> None:
    """ResultEvent 联合类型必须包含全部 11 种 event。"""
    # 构造 11 个不同类型实例，确认都能赋值给 ResultEvent
    events: list[ResultEvent] = [
        MessageEvent(turn_id="t", seq=0, event_id="e", delta=""),
        ToolCallEvent(
            turn_id="t", seq=0, event_id="e",
            tool_name="x", tool_call_id="tc", arguments={},
        ),
        ToolResultEvent(
            turn_id="t", seq=0, event_id="e",
            tool_call_id="tc", output={}, is_error=False, latency_ms=0,
        ),
        SkillInvocationEvent(
            turn_id="t", seq=0, event_id="e",
            invocation_id="i", skill="s", status="started",
        ),
        MemoryWriteEvent(
            turn_id="t", seq=0, event_id="e",
            layer="l1", source_turn_id="s", preview="",
        ),
        KnowledgeSearchEvent(
            turn_id="t", seq=0, event_id="e",
            query_hash="h", hits=[], citations=[], degraded=False,
        ),
        ContextCompactedEvent(
            turn_id="t", seq=0, event_id="e",
            tokens_before=0, tokens_after=0, removed_ids=[],
        ),
        ApprovalRequiredEvent(
            turn_id="t", seq=0, event_id="e",
            approval_id="a", tool_call_id="tc", tool="",
            args_preview="", reason="", expires_at="2026-10-15T10:15:00Z",
        ),
        UsageEvent(
            turn_id="t", seq=0, event_id="e",
            input_tokens=0, output_tokens=0, cache_tokens=0,
            cost_usd=None, cost_unknown=True,
            tenant_id="t", workspace_id="w", user_id="u",
            agent_id="a", agent_version="v", model_version="m",
            retry_count=0,
        ),
        DoneEvent(
            turn_id="t", seq=0, event_id="e",
            final_message="", status="succeeded",
            agent_version="v", model_version="m",
        ),
        ErrorEvent(
            turn_id="t", seq=0, event_id="e",
            error_code="INTERNAL_ERROR", safe_message="",
        ),
    ]
    assert len(events) == 11


def test_event_models_are_frozen() -> None:
    """事件模型必须不可变（避免在图状态中意外修改）。"""
    e = MessageEvent(turn_id="t", seq=0, event_id="e", delta="hi")
    try:
        e.delta = "modified"  # type: ignore[misc]
    except Exception:
        return  # expected
    raise AssertionError("event model should be frozen")