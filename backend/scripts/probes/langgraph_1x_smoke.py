"""LangGraph 1.x 兼容性 smoke 测试（§2.5 阻塞 1）。

验证以下 1.x 行为与现有 `runner.py:161` 的 `while True` 循环可替换为 graph 节点：

1. `StateGraph.add_node` / `add_edge` / `add_conditional_edges` 1.x 签名
2. `MemorySaver` 仍可作为 checkpointer（运行时用 Postgres 替换）
4. `graph.compile()` 在 1.x 下可成功
4. `astream_events(version="v2")` 仍能产出 `on_chain_start` 事件
5. `interrupt` 与 `Command(resume=...)` 1.x 协议存在

不在本 smoke 中验证的项（需 PG 才能跑）：
- PostgresSaver / PostgresStore
- 进程重启后从 checkpoint 恢复
"""

from __future__ import annotations

import asyncio
import sys
from typing import Annotated, Any

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.types import Command, interrupt
from typing_extensions import TypedDict


# ---------------------------------------------------------------------------
# 1. StateGraph 1.x API 验证
# ---------------------------------------------------------------------------


class _SmokeState(TypedDict, total=False):
    """最小状态类型，验证 add_messages reducer 在 1.x 下签名不变。"""

    messages: Annotated[list[Any], add_messages]
    counter: int


def _echo(state: _SmokeState) -> _SmokeState:
    return {"counter": (state.get("counter") or 0) + 1}


def _conditional(state: _SmokeState) -> str:
    return "loop" if (state.get("counter") or 0) < 3 else END


def build_smoke_graph() -> Any:
    """构建一个最小可编译图，验证 1.x 签名。"""
    g = StateGraph(_SmokeState)
    g.add_node("echo", _echo)
    g.add_edge(START, "echo")
    g.add_conditional_edges("echo", _conditional, {"loop": "echo", END: END})
    return g.compile(checkpointer=InMemorySaver())


# ---------------------------------------------------------------------------
# 2. interrupt + Command(resume=...) 协议验证
# ---------------------------------------------------------------------------


class _InterruptState(TypedDict, total=False):
    approved: bool
    value: str | None


def _human_in_loop(state: _InterruptState) -> _InterruptState:
    approved = interrupt({"question": "approve?"})
    return {"approved": bool(approved), "value": state.get("value")}


def build_interrupt_graph() -> Any:
    g = StateGraph(_InterruptState)
    g.add_node("human", _human_in_loop)
    g.add_edge(START, "human")
    return g.compile(checkpointer=InMemorySaver())


# ---------------------------------------------------------------------------
# 3. 跑通：invoke + astream_events(version="v2")
# ---------------------------------------------------------------------------


async def _run_smoke() -> dict[str, Any]:
    """跑 smoke，返回可序列化的状态摘要。"""
    out: dict[str, Any] = {}

    # (1) 基本图编译 + invoke
    compiled = build_smoke_graph()
    final = compiled.invoke({"counter": 0}, config={"configurable": {"thread_id": "t-1"}})
    out["invoke_final_counter"] = final.get("counter")

    # (2) astream_events version=v2 验证事件可产出
    event_kinds: set[str] = set()
    async for ev in compiled.astream_events(
        {"counter": 0}, config={"configurable": {"thread_id": "t-2"}}, version="v2"
    ):
        event_kinds.add(ev["event"])
    out["astream_event_kinds"] = sorted(event_kinds)

    # (3) interrupt + Command(resume=...)
    interrupt_compiled = build_interrupt_graph()
    cfg = {"configurable": {"thread_id": "t-3"}}

    # 第一次 invoke：触发 interrupt
    first_chunks: list[Any] = []
    async for chunk in interrupt_compiled.astream({"value": "hi"}, config=cfg):
        first_chunks.append(chunk)
    out["interrupt_first_chunks"] = [str(c) for c in first_chunks]

    # 用 Command(resume=True) 恢复
    resumed = await interrupt_compiled.ainvoke(Command(resume=True), config=cfg)
    out["interrupt_resumed_state"] = dict(resumed)

    return out


def main() -> int:
    result = asyncio.run(_run_smoke())
    import json
    print(json.dumps(result, indent=2, ensure_ascii=False))

    # 验收
    if result.get("invoke_final_counter") != 3:
        print("FAIL: invoke did not loop 3 times", file=sys.stderr)
        return 1
    if "on_chain_start" not in result.get("astream_event_kinds", []):
        print("FAIL: astream_events v2 did not produce on_chain_start", file=sys.stderr)
        return 1
    if result.get("interrupt_resumed_state", {}).get("approved") is not True:
        print("FAIL: Command(resume=True) did not propagate", file=sys.stderr)
        return 1

    print("OK: LangGraph 1.x smoke passed", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())