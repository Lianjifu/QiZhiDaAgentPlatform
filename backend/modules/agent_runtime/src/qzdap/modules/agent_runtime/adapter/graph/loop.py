"""Bounded ReAct loop compiled as a LangGraph StateGraph."""

from __future__ import annotations

from typing import Any, Literal

from langgraph.graph import END, START, StateGraph

from qzdap.modules.agent_runtime.adapter.graph.state import LoopState, tool_signature

HARD_MAX_STEPS = 16


def next_route(state: LoopState) -> Literal["tools", "end"]:
    if state.get("pending_approval"):
        return "end"
    if int(state.get("step") or 0) >= int(state.get("max_steps") or 8):
        return "end"
    messages = list(state.get("messages") or [])
    if not messages:
        return "end"
    last = messages[-1]
    if last.get("role") == "assistant" and last.get("tool_calls"):
        return "tools"
    return "end"


def apply_stall_guard(state: LoopState, calls: list[dict[str, Any]]) -> LoopState:
    sigs = []
    for call in calls:
        name = str(call.get("name") or (call.get("function") or {}).get("name") or "")
        args = call.get("arguments") or (call.get("function") or {}).get("arguments") or {}
        if not isinstance(args, dict):
            args = {}
        sigs.append(tool_signature(name, args))
    joined = "|".join(sigs)
    stall = int(state.get("stall_count") or 0)
    if joined and joined == state.get("last_tool_sig"):
        stall += 1
    else:
        stall = 0
    messages = list(state.get("messages") or [])
    if stall >= 2:
        messages.append(
            {
                "role": "system",
                "content": "相同工具连续空转，请直接给出当前已知信息的最终回答，不要再调用工具。",
            }
        )
        return {
            **state,
            "messages": messages,
            "stall_count": stall,
            "last_tool_sig": joined,
            "pending_approval": None,
        }
    return {**state, "stall_count": stall, "last_tool_sig": joined}


def compile_loop_graph(*, llm_node, tools_node):
    graph = StateGraph(LoopState)
    graph.add_node("llm", llm_node)
    graph.add_node("tools", tools_node)
    graph.add_edge(START, "llm")
    graph.add_conditional_edges("llm", next_route, {"tools": "tools", "end": END})
    graph.add_edge("tools", "llm")
    return graph.compile()


__all__ = ["HARD_MAX_STEPS", "apply_stall_guard", "compile_loop_graph", "next_route"]
