"""Tests for SessionState TypedDict (§4.1 / §2.5 阻塞 3 19 节点对齐)。"""

from __future__ import annotations

from qzdap_agent_runtime.graph import (
    SCHEMA_VERSION,
    PendingApproval,
    ResultState,
    Route,
    RuntimeErrorState,
    SessionState,
    Todo,
    ToolCallState,
    ToolResultState,
    UsageState,
)


# ---------------------------------------------------------------------------
# SessionState 字段完整性
# ---------------------------------------------------------------------------


def test_schema_version_is_current() -> None:
    assert SCHEMA_VERSION == 1


def test_session_state_has_19_node_aligned_fields() -> None:
    """SessionState 必须覆盖 §13.2 表中 19 节点对应的状态字段。"""
    expected_required: set[str] = {
        # 标识 / 元数据（节点 1-3）
        "schema_version",
        "tenant_id",
        "workspace_id",
        "session_id",
        "turn_id",
        "thread_id",
        "idempotency_key",
        # 修订（节点 2）
        "revision",
        "expected_revision",
        # trace / agent 版本（节点 5）
        "trace_id",
        "agent_id",
        "agent_version",
        "model_version",
        # 消息 / 摘要 / 上下文（节点 6/7/8）
        "messages",
        "rolling_summary",
        "context_manifest",
        # 召回（节点 6）
        "memory_hits",
        "knowledge_hits",
        # 路由 / 工具（节点 9/11/12/13/14）
        "route",
        "pending_approval",
        "tool_calls",
        "tool_results",
        "todos",
        # 结果 / 用量 / 错误（节点 15-18）
        "result",
        "usage",
        "emitted_seq",
        "errors",
        # 降级标志
        "degraded",
    }
    annotations = set(SessionState.__annotations__.keys())
    missing = expected_required - annotations
    assert not missing, f"SessionState missing fields: {missing}"


def test_session_state_messages_uses_add_messages_reducer() -> None:
    """messages 字段必须使用 add_messages reducer（§4.1）。"""
    from langgraph.graph.message import add_messages

    # TypedDict 的 Annotated 类型不能用 getattr 直接拿；用 __annotations__ 查源
    import typing

    hints = typing.get_type_hints(SessionState, include_extras=True)
    msg_hint = hints.get("messages")
    # Annotated[list[Any], add_messages] 的 get_type_hints 形式：list[typing.Any]
    assert msg_hint is not None
    # 元数据保留在 __metadata__ 中
    assert hasattr(msg_hint, "__metadata__")
    assert add_messages in msg_hint.__metadata__


# ---------------------------------------------------------------------------
# 子类型
# ---------------------------------------------------------------------------


class TestRoute:
    def test_route_default_keys(self) -> None:
        route: Route = {}
        # total=False 允许缺省；这里只验证可构造
        assert route == {}

    def test_route_full(self) -> None:
        route: Route = {
            "deep_task": True,
            "task_kind": "DEEP_RESEARCH",
            "rule_version": "v1",
            "classifier": "heuristic",
            "confidence": 0.95,
            "candidates": ["deep_research", "multi_step_code"],
            "reason": "long context + tools > 5",
        }
        assert route["deep_task"] is True


class TestPendingApproval:
    def test_pending_approval_construction(self) -> None:
        pa: PendingApproval = {
            "approval_id": "apr-001",
            "tool_call_id": "tc-001",
            "tool_name": "send_email",
            "arguments_hash": "sha256:abc",
            "policy_id": "pol-pii-outbound",
            "requester": "user-1",
            "requested_at": "2026-10-15T10:00:00Z",
            "expires_at": "2026-10-15T10:15:00Z",
        }
        assert pa["approval_id"] == "apr-001"


class TestUsageState:
    def test_usage_state_with_cost_unknown(self) -> None:
        u: UsageState = {
            "input_tokens": 1200,
            "output_tokens": 800,
            "cache_tokens": 200,
            "cost_usd": None,
            "cost_unknown": True,
            "attribution_status": "degraded",
        }
        assert u["cost_unknown"] is True


class TestToolCallStateAndResultState:
    def test_tool_call_state(self) -> None:
        tc: ToolCallState = {
            "tool_call_id": "tc-1",
            "tool_name": "search_kb",
            "arguments": {"query": "q"},
            "risk": "low",
            "status": "succeeded",
            "result_ref": "idem-key-1",
            "latency_ms": 120,
            "retry_count": 0,
        }
        assert tc["risk"] == "low"

    def test_tool_result_state_with_pointer(self) -> None:
        tr: ToolResultState = {
            "tool_call_id": "tc-1",
            "content": "<summary>",
            "is_error": False,
            "raw_size_bytes": 80_000,
            "pointer": "s3://bucket/obj",
        }
        assert tr["raw_size_bytes"] > 64 * 1024

    def test_result_state(self) -> None:
        r: ResultState = {
            "final_message": "done",
            "status": "succeeded",
            "error_code": None,
            "agent_version": "v1.0",
            "model_version": "gpt-5-2025-01",
        }
        assert r["status"] == "succeeded"

    def test_runtime_error_state(self) -> None:
        e: RuntimeErrorState = {
            "node": "execute",
            "error_code": "TOOL_TIMEOUT",
            "message": "tool timed out",
            "trace_id": "tr-1",
            "retriable": True,
            "occurred_at": "2026-10-15T10:00:00Z",
        }
        assert e["retriable"] is True

    def test_todo(self) -> None:
        t: Todo = {
            "id": "t-1",
            "status": "in_progress",
            "content": "investigate the dataset",
            "assigned_subagent": "research-1",
        }
        assert t["status"] == "in_progress"