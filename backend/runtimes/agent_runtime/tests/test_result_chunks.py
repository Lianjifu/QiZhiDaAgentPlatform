"""**结果事件的唯一实现** ✓ —— 一律产出对外 chunk ✓（A-39 ✓）。

⚠️ **以前这里测的是 16 种内部事件类型** ✓ —— 它们**已删** ✓（两套形状 =
两处要改 ✗✗）→ 现在测的是**工厂** ✓（每种 kind 产出什么 chunk ✓）。

⚠️ **重点是「字段没丢」** ✓（方案 A-39 的提醒 ✓）—— 内部事件多带的东西
（usage 的 6 维 ✓ / error 的 ``detailed`` ✓ / ``event_id`` ✓ …）**必须还在**
✓ —— 那是数据丢失 ✗✗。
"""

from __future__ import annotations

from qzdap_agent_runtime.result import to_chunk

_TURN = "11111111-1111-1111-1111-111111111111"


def _chunk(event_type: str, payload: dict | None = None):
    return to_chunk(
        event_type=event_type,
        payload=payload or {},
        turn_id=_TURN,
        seq=1,
        event_id="e-1",
    )


def test_the_message_chunk_carries_the_text() -> None:
    chunk = _chunk("message", {"content": "你好"})
    assert chunk.kind == "message"
    assert chunk.content == "你好"
    assert chunk.event_id == "e-1"


def test_the_tool_call_chunk_keeps_the_arguments() -> None:
    chunk = _chunk(
        "tool_call",
        {
            "tool_name": "search_kb",
            "tool_call_id": "22222222-2222-2222-2222-222222222222",
            "arguments": {"q": "test"},
        },
    )
    assert chunk.kind == "tool_call"
    assert chunk.tool_name == "search_kb"
    assert chunk.arguments == {"q": "test"}


def test_the_tool_result_chunk_keeps_the_latency() -> None:
    chunk = _chunk(
        "tool_result",
        {
            "tool_call_id": "22222222-2222-2222-2222-222222222222",
            "output": {"hits": []},
            "is_error": False,
            "latency_ms": 120,
        },
    )
    assert chunk.kind == "tool_result"
    assert chunk.latency_ms == 120


def test_the_skill_invocation_chunk_keeps_the_skill_name() -> None:
    chunk = _chunk(
        "skill_invocation",
        {
            "invocation_id": "33333333-3333-3333-3333-333333333333",
            "skill": "pdf-summarize",
            "status": "started",
        },
    )
    assert chunk.kind == "skill_invocation"
    assert chunk.skill_name == "pdf-summarize"


def test_the_memory_write_chunk_keeps_the_source_turn() -> None:
    chunk = _chunk(
        "memory_write",
        {"layer": "l2", "source_turn_id": "t-0", "preview": "用户偏好中文"},
    )
    assert chunk.kind == "memory_write"
    assert chunk.layer == "l2"
    assert chunk.source_turn_id == "t-0"


def test_the_knowledge_search_chunk_keeps_the_query_hash() -> None:
    chunk = _chunk(
        "knowledge_search",
        {"query_hash": "hash-x", "hits": [{"id": "k-1"}], "citations": ["doc://k-1"]},
    )
    assert chunk.kind == "knowledge_search"
    assert chunk.query_hash == "hash-x"
    assert chunk.citations == ["doc://k-1"]


def test_the_context_compacted_chunk_keeps_the_removed_ids() -> None:
    chunk = _chunk(
        "context_compacted",
        {"tokens_before": 20_000, "tokens_after": 8_000, "removed_ids": ["m-1", "m-2"]},
    )
    assert chunk.kind == "context_compacted"
    assert chunk.tokens_after < chunk.tokens_before
    assert chunk.removed_ids == ["m-1", "m-2"]


def test_the_approval_chunk_keeps_the_expiry() -> None:
    chunk = _chunk(
        "approval_required",
        {
            "approval_id": "44444444-4444-4444-4444-444444444444",
            "tool": "send_email",
            "args_preview": "to: x@y",
            "reason": "pii outbound",
            "expires_at": "2026-10-15T10:15:00Z",
        },
    )
    assert chunk.kind == "approval_required"
    assert chunk.tool_name == "send_email"
    assert chunk.expires_at == "2026-10-15T10:15:00Z"
    assert chunk.arguments == {"preview": "to: x@y"}


def test_the_usage_chunk_keeps_the_six_dimensions() -> None:
    """**usage 的 6 个归属维度不能丢** ✓（成本要按维度归集 ✓）。"""
    chunk = _chunk(
        "usage",
        {
            "input_tokens": 1200,
            "output_tokens": 800,
            "cache_tokens": 200,
            "cost_usd": 0.05,
            "tenant_id": "tnt-1",
            "workspace_id": "ws-1",
            "user_id": "u-1",
            "agent_id": "agt-1",
            "agent_version": "v1.0",
            "model_version": "gpt-5-2025-01",
            "retry_count": 2,
        },
    )
    assert chunk.kind == "usage"
    for required in (
        "tenant_id",
        "workspace_id",
        "user_id",
        "agent_id",
        "agent_version",
        "model_version",
    ):
        assert getattr(chunk, required), f"missing {required}"
    assert chunk.retry_count == 2


def test_the_done_chunk_keeps_the_status_and_the_versions() -> None:
    chunk = _chunk(
        "done",
        {
            "final_message": "completed",
            "status": "succeeded",
            "agent_version": "v1.0",
            "model_version": "gpt-5-2025-01",
        },
    )
    assert chunk.kind == "done"
    assert chunk.status == "succeeded"
    assert chunk.agent_version == "v1.0"


def test_the_error_chunk_keeps_the_details_out_of_the_user_text() -> None:
    chunk = _chunk(
        "error",
        {
            "error_code": "TOOL_TIMEOUT",
            "safe_message": "工具执行超时，请稍后重试",
            "detailed": "full traceback ...",
        },
    )
    assert chunk.kind == "error"
    assert chunk.code == "TOOL_TIMEOUT"
    assert chunk.message == "工具执行超时，请稍后重试"
    assert chunk.detailed == "full traceback ..."


def test_the_plan_and_artifact_chunks_keep_their_payload() -> None:
    plan = _chunk(
        "plan_proposed",
        {
            "plan_id": "55555555-5555-5555-5555-555555555555",
            "title": "计划",
            "steps": [{"id": "1", "title": "第一步"}],
        },
    )
    assert plan.kind == "plan_proposed"
    assert plan.title == "计划"
    assert plan.steps

    artifact = _chunk(
        "artifact_ready",
        {
            "artifact_id": "66666666-6666-6666-6666-666666666666",
            "kind_": "markdown",
            "name": "报告",
            "mime": "text/markdown",
            "size_bytes": 12,
            "download_path": "/api/artifacts/1/content",
        },
    )
    assert artifact.kind == "artifact_ready"
    assert artifact.name == "报告"
    assert artifact.download_path == "/api/artifacts/1/content"


def test_an_unknown_kind_falls_back_to_an_error_chunk() -> None:
    """**未知类型不抛** ✓（投递失败要能被 worker 记成 FAILED ✓）。"""
    chunk = _chunk("no_such_kind")
    assert chunk.kind == "error"
    assert chunk.detailed and "no_such_kind" in chunk.detailed
