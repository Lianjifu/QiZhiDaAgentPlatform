"""`build_session_graph()` — 19 节点 StateGraph 装配（§3.2 / §13.2）。

Stage 1 退出条件（§8）：
- 纯内存 fake 可编译图
- 通过单元测试

`build_session_graph()` 返回 LangGraph `CompiledStateGraph`：

- 主路径 add_node 17 次固定（1–12, 15–19）
- 条件挂载 2 次（13 deep_agent_plan / 14 subagent，仅 deep_task=true）
- InMemorySaver 作为 checkpointer（生产用 PostgresSaver 替换，Stage 2）
- add_edge 顺序：START → 1 → 2 → … → 9 → 10 → 11/13 条件分支 → 12/14 → 10（loop）→ 15 → 16 → 17 → 18 → 19 → END
"""

from __future__ import annotations

from typing import Any

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from .nodes import (
    acquire_turn_lock,
    agent,
    assemble_context,
    compact_if_needed,
    compact_tool_result,
    deep_agent_plan,
    emit_result,
    execute,
    governance,
    load_agent_context,
    load_checkpoint,
    loop_should_continue,
    normalize_input,
    persist_result,
    recall_memory_and_knowledge,
    release_turn_lock,
    remember,
    route,
    should_take_deep_branch,
    subagent,
    write_turn_record,
)
from .state import SessionState


def build_session_graph(*, checkpointer: Any | None = None) -> Any:
    """构造 19 节点 StateGraph 并编译。

    Args:
        checkpointer: LangGraph checkpointer 实例；默认 `InMemorySaver()`
            （Stage 1 退出条件）。生产用 `PostgresSaver`（Stage 2）。

    Returns:
        LangGraph `CompiledStateGraph`，可 `.invoke()` / `.astream()`。
    """
    if checkpointer is None:
        checkpointer = InMemorySaver()

    g = StateGraph(SessionState)

    # ---- 节点挂载：17 次固定 + 2 次条件 ----
    # 1-9 外层线性段
    g.add_node("normalize_input", normalize_input)
    g.add_node("acquire_turn_lock", acquire_turn_lock)
    g.add_node("load_checkpoint", load_checkpoint)
    g.add_node("write_turn_record", write_turn_record)
    g.add_node("load_agent_context", load_agent_context)
    g.add_node("recall_memory_and_knowledge", recall_memory_and_knowledge)
    g.add_node("assemble_context", assemble_context)
    g.add_node("compact_if_needed", compact_if_needed)
    g.add_node("route", route)

    # 10-14 Agent Loop + Deep Agents 条件分支
    g.add_node("agent", agent)
    g.add_node("governance", governance)
    g.add_node("execute", execute)
    g.add_node("deep_agent_plan", deep_agent_plan)
    g.add_node("subagent", subagent)

    # 15-19 收尾段
    g.add_node("remember", remember)
    g.add_node("persist_result", persist_result)
    g.add_node("emit_result", emit_result)
    g.add_node("compact_tool_result", compact_tool_result)
    g.add_node("release_turn_lock", release_turn_lock)

    # ---- 边：外层线性段（顺序） ----
    g.add_edge(START, "normalize_input")
    g.add_edge("normalize_input", "acquire_turn_lock")
    g.add_edge("acquire_turn_lock", "load_checkpoint")
    g.add_edge("load_checkpoint", "write_turn_record")
    g.add_edge("write_turn_record", "load_agent_context")
    g.add_edge("load_agent_context", "recall_memory_and_knowledge")
    g.add_edge("recall_memory_and_knowledge", "assemble_context")
    g.add_edge("assemble_context", "compact_if_needed")
    g.add_edge("compact_if_needed", "route")

    # ---- 边：route 后条件分支 ----
    g.add_conditional_edges(
        "route",
        should_take_deep_branch,
        {
            "simple": "agent",
            "deep": "deep_agent_plan",
        },
    )

    # ---- 边：Agent Loop 内循环 ----
    # simple 路径：agent → (governance → execute → agent 循环) → remember
    # **agent 节点只走条件边**：loop_should_continue 决定 continue→governance / exit→remember
    # 不同时挂 add_edge(agent → governance)，否则两条出边冲突导致递归死循环。
    g.add_edge("governance", "execute")
    g.add_edge("execute", "agent")  # execute 完成后回到 agent
    g.add_conditional_edges(
        "agent",
        loop_should_continue,
        {
            "continue": "governance",
            "exit": "remember",
        },
    )

    # deep 路径：deep_agent_plan → subagent → agent（摘要回主图）
    g.add_edge("deep_agent_plan", "subagent")
    g.add_edge("subagent", "agent")  # 摘要回主 agent

    # ---- 边：收尾段（顺序） ----
    g.add_edge("remember", "persist_result")
    g.add_edge("persist_result", "emit_result")
    g.add_edge("emit_result", "compact_tool_result")
    g.add_edge("compact_tool_result", "release_turn_lock")
    g.add_edge("release_turn_lock", END)

    return g.compile(checkpointer=checkpointer)


__all__ = ["build_session_graph"]