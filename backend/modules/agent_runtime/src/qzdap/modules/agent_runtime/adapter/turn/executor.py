"""``TurnExecutorPort`` 的实现 —— 把现役的 graph runner 包成端口。

⚠️ **执行器本身还没换** —— 现在跑的还是 ``modules`` 的
``SessionGraphRunner``（旧手写循环，台账 **X17**）。它归 **Agent 层**的
A-26 退役（改接 LangGraph 图）✓ —— Session 层只负责**编排**，
不碰「循环怎么跑」✓。

⚠️ 因此这里是**适配**而不是「搬」：``SessionGraphRunner.run_turn`` 的参数
是 ``**kwargs``，本适配器把契约层的 :class:`TurnRequest` 翻译过去 ✓。
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from typing import Any

from qzdap_agent_runtime.session.turn_runner import TurnRequest


class SessionGraphExecutor:
    """执行器适配器 —— 契约层的请求 → graph runner 的参数 ✓。"""

    def __init__(self, graph: Any) -> None:
        self._graph = graph

    def run(self, *, request: TurnRequest) -> AsyncIterator[Any]:
        """跑一轮 —— 产出 chunk 流 ✓。

        ⚠️ **resume 只在「有审批挂起」或「显式恢复」时传** —— 否则 graph 会
        拿着上一轮的残留状态重跑 ✓（与旧实现同语义）。
        """
        graph_state = dict(request.graph_state or {})
        resume = request.resume
        merged = {**graph_state, **(resume or {})} if resume else graph_state
        return self._graph.run_turn(
            tenant_id=request.tenant_id,
            workspace_id=request.workspace_id,
            owner_id=request.owner_id,
            turn_id=request.turn_id,
            user_input=request.user_input,
            history=request.history,
            agent=request.agent.raw,
            model=request.model,
            route_id=request.route_id,
            rolling_summary=request.rolling_summary,
            resume=merged if (merged.get("pending_approval") or resume) else None,
            session_id=request.session_id,
            parent_span_context=request.parent_span_context,
        )

    def latest_state(self) -> Mapping[str, Any]:
        """执行器的最新状态（续传状态 / 摘要）✓。"""
        return dict(getattr(self._graph, "last_loop_state", {}) or {})


__all__ = ["SessionGraphExecutor"]
