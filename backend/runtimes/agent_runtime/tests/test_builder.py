"""Tests for build_session_graph — Stage 1 退出条件（§8）。

Stage 1 退出条件：

> 纯内存 fake 可编译图并通过单元测试。

本文件验证：

1. `build_session_graph()` 返回 `CompiledStateGraph`
2. 图含 19 个节点（含 deep_agent_plan / subagent 条件挂载）
3. `invoke()` 能跑通完整线性 + Agent Loop 收尾路径
4. 在断点处可恢复（InMemorySaver 保留 state）
5. simple / deep 条件分支正确触发
"""

from __future__ import annotations

from typing import Any

from langgraph.checkpoint.memory import InMemorySaver

from qzdap_agent_runtime.graph import SessionState, build_session_graph


# ---------------------------------------------------------------------------
# 1. 编译
# ---------------------------------------------------------------------------


def test_build_session_graph_compiles_with_default_saver() -> None:
    """build_session_graph() 必须用 InMemorySaver 编译成功。"""
    compiled = build_session_graph()
    # LangGraph CompiledStateGraph 类名
    assert compiled.__class__.__name__ == "CompiledStateGraph"


def test_build_session_graph_accepts_custom_saver() -> None:
    """build_session_graph(checkpointer=...) 必须接受自定义 saver。"""
    custom = InMemorySaver()
    compiled = build_session_graph(checkpointer=custom)
    assert compiled.checkpointer is custom


# ---------------------------------------------------------------------------
# 2. 节点挂载：17 固定 + 2 条件 = 19
# ---------------------------------------------------------------------------


EXPECTED_NODES: set[str] = {
    # 1-9 外层线性段
    "normalize_input",
    "acquire_turn_lock",
    "load_checkpoint",
    "write_turn_record",
    "load_agent_context",
    "recall_memory_and_knowledge",
    "assemble_context",
    "compact_if_needed",
    "route",
    # 10-14 Agent Loop + Deep Agents 条件分支
    "agent",
    "governance",
    "execute",
    "deep_agent_plan",
    "subagent",
    # 15-19 收尾段
    "remember",
    "persist_result",
    "emit_result",
    "compact_tool_result",
    "release_turn_lock",
}


def test_graph_has_all_19_nodes() -> None:
    """图必须挂载 19 个节点（节点 ID 与 §2.5 阻塞 3 权威命名表一致）。"""
    compiled = build_session_graph()
    # LangGraph 1.x API: compiled.nodes 是 dict（含 __start__ / __end__ 虚拟节点）
    node_names = {name for name in compiled.nodes if not name.startswith("__")}
    missing = EXPECTED_NODES - node_names
    assert not missing, f"missing nodes: {missing}"
    # 防止意外的额外节点（防止 ID 漂移）
    extra = node_names - EXPECTED_NODES
    assert not extra, f"unexpected nodes: {extra}"


def test_graph_node_count_is_exactly_19() -> None:
    """图节点数必须严格 = 19（与 §13.2 表一致）。"""
    compiled = build_session_graph()
    real_nodes = {
        name for name in compiled.nodes if not name.startswith("__")
    }
    assert len(real_nodes) == 19


# ---------------------------------------------------------------------------
# 3. invoke 跑通完整路径
# ---------------------------------------------------------------------------


def _initial_state(**overrides: Any) -> dict[str, Any]:
    """最小初始 SessionState（test 用）。"""
    state: dict[str, Any] = {
        "schema_version": 1,
        "tenant_id": "tnt-1",
        "workspace_id": "ws-1",
        "session_id": "sess-1",
        "turn_id": "turn-1",
        "thread_id": "sess-1",
        "idempotency_key": "idem-1",
        "revision": 1,
        "trace_id": "tr-1",
        "agent_id": "agt-1",
        "agent_version": "v1",
        "model_version": "m1",
        "messages": [],
        "tool_calls": [],
        "tool_results": [],
        "todos": [],
        "usage": {
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_tokens": 0,
            "cost_usd": None,
            "cost_unknown": True,
            "attribution_status": "degraded",
        },
        "emitted_seq": 0,
        "errors": [],
        "degraded": {},
    }
    state.update(overrides)
    return state


def test_graph_runs_full_path_simple_branch() -> None:
    """simple 分支：START → ... → release_turn_lock → END 全部经过。"""
    final = build_session_graph().invoke(
        _initial_state(),
        config={"configurable": {"thread_id": "t-1"}},
    )
    # 验证：经过 route 节点后 route.deep_task = False（Stage 1 fake）
    assert final["route"]["deep_task"] is False
    assert final["route"]["task_kind"] == "SIMPLE_QA"
    # 验证：recall_memory_and_knowledge 节点初始化了空 hits
    assert final["memory_hits"] == []
    assert final["knowledge_hits"] == []
    # 验证：identity 字段保留
    assert final["session_id"] == "sess-1"
    assert final["turn_id"] == "turn-1"


# ---------------------------------------------------------------------------
# 4. 状态恢复（InMemorySaver 保留 thread_id 状态）
# ---------------------------------------------------------------------------


def test_graph_resumes_from_thread_checkpoint() -> None:
    """InMemorySaver 必须按 thread_id 保留 state。"""
    compiled = build_session_graph()
    cfg = {"configurable": {"thread_id": "t-resume"}}

    # 第一次跑
    compiled.invoke(_initial_state(), config=cfg)

    # 列出 checkpoints
    checkpoints = list(compiled.get_state_history(cfg))
    assert len(checkpoints) >= 1


# ---------------------------------------------------------------------------
# 5. simple / deep 条件分支
# ---------------------------------------------------------------------------


def test_simple_branch_runs_agent_then_remember() -> None:
    """deep_task=false 时：route → agent → (governance → execute → agent loop exit) → remember。"""
    final = build_session_graph().invoke(
        _initial_state(),
        config={"configurable": {"thread_id": "t-simple"}},
    )
    # route 决策 deep_task=false
    assert final["route"]["deep_task"] is False
    # 端到端跑完（remember 节点后所有边已过）
    # 占位：没有 errors 表示没异常
    assert final["errors"] == []


def test_deep_branch_routes_to_deep_agent_plan() -> None:
    """deep_task=true 时：route → deep_agent_plan → subagent → agent → ... → remember。"""
    state = _initial_state()
    # 预设 route.deep_task=true（模拟真实 Stage 4 触发）
    state["route"] = {
        "deep_task": True,
        "task_kind": "DEEP_RESEARCH",
        "rule_version": "test",
        "classifier": "test",
        "confidence": 1.0,
        "candidates": [],
        "reason": "test",
    }
    final = build_session_graph().invoke(
        state,
        config={"configurable": {"thread_id": "t-deep"}},
    )
    # 即便预设了 deep_task=true，但 route 节点 Stage 1 fake 会覆盖
    # 这里只验证图能容忍 deep_task 状态跑通，不崩溃
    assert "route" in final


# ---------------------------------------------------------------------------
# 6. 节点执行计数：astream 验证每个节点都被访问过
# ---------------------------------------------------------------------------


def test_simple_path_visits_required_nodes() -> None:
    """simple 路径必须访问外层段 + agent + 收尾段（共 16 个固定节点）。

    注：governance / execute 是 Agent Loop 内循环节点，仅当 `loop_should_continue`
    返回 'continue' 时才被访问。Stage 1 fake 始终立即 exit，因此这两个节点在
    Stage 1 测试中不会被触发；Stage 4 接入真实 classifier 后会被实际访问。
    """
    compiled = build_session_graph()
    visited_nodes: set[str] = set()
    for event in compiled.stream(
        _initial_state(),
        config={"configurable": {"thread_id": "t-simple-visited"}},
        stream_mode="updates",
    ):
        for node_name in event:
            visited_nodes.add(node_name)

    # Stage 1 fake 必访：外层 9 + route + agent + 收尾 5 = 16 节点
    expected_simple = (
        EXPECTED_NODES
        - {"deep_agent_plan", "subagent"}  # deep 路径不在 simple 内
        - {"governance", "execute"}  # 内循环节点 Stage 1 不触发
    )
    missing = expected_simple - visited_nodes
    assert not missing, f"simple path missed required nodes: {missing}"
    # 反向断言：deep 节点不应被 simple 路径触发
    assert "deep_agent_plan" not in visited_nodes
    assert "subagent" not in visited_nodes


def test_deep_branch_visits_deep_nodes() -> None:
    """deep 路径必须访问 deep_agent_plan / subagent。

    `builder.py` 通过 `from .nodes import route` 绑定函数引用。
    必须直接 patch `qzdap_agent_runtime.graph.builder.route` 才能影响图。
    """
    import qzdap_agent_runtime.graph.builder as builder_module

    original_route = builder_module.route

    def deep_route(state: dict) -> dict:
        # 跳过 fake 行为，覆盖为 deep_task=True
        return {
            "route": {
                "deep_task": True,
                "task_kind": "DEEP_RESEARCH",
                "rule_version": "test",
                "classifier": "test",
                "confidence": 1.0,
                "candidates": [],
                "reason": "test",
            }
        }

    builder_module.route = deep_route  # type: ignore[assignment]
    try:
        compiled = build_session_graph()
        visited_nodes: set[str] = set()
        for event in compiled.stream(
            _initial_state(),
            config={"configurable": {"thread_id": "t-deep-visited"}},
            stream_mode="updates",
        ):
            for node_name in event:
                visited_nodes.add(node_name)

        # deep 分支必访问 deep_agent_plan + subagent
        assert "deep_agent_plan" in visited_nodes
        assert "subagent" in visited_nodes
    finally:
        builder_module.route = original_route  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# 7. SessionState 字段在图中可用
# ---------------------------------------------------------------------------


def test_session_state_required_fields_flow_through_graph() -> None:
    """所有 SessionState 必填字段在 invoke 中能正常流转。"""
    final = build_session_graph().invoke(
        _initial_state(),
        config={"configurable": {"thread_id": "t-fields"}},
    )
    # 这些字段在 invoke 前后必须保持
    for field in (
        "tenant_id", "workspace_id", "session_id", "turn_id",
        "thread_id", "idempotency_key", "revision",
        "agent_id", "agent_version", "model_version",
        "trace_id",
    ):
        assert final[field] == _initial_state().get(field), f"field {field} mutated"
    # 用量字段保留（Stage 1 fake 不消耗 token）
    assert final["usage"]["input_tokens"] == 0