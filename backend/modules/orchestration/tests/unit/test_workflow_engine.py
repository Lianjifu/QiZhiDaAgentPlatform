"""**工作流执行引擎** 的单测 —— 真的走一遍图 ✓。

⚠️ 这里测的是**编排语义** ✓ —— 工具 / 智能体的执行口是替身 ✓（真库与真
工具在集成测试里验 ✓）。

覆盖：

- 触发 → 工具 → 结束 ✓（变量按名字往下传 ✓）；
- 条件分支 ✓（命中哪个出口 ✓）；
- 智能体节点 ✓（把输入拼成提示 ✓）；
- **没有端口就不执行那类节点** ✓（报错 ✓ —— 不假装跑过 ✓）；
- 节点失败就停 ✓（结果里写清楚停在哪一步 ✓）；
- 图里有环不会把进程跑死 ✓。
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest

from qzdap.modules.orchestration.application.engine import WorkflowEngine
from qzdap.modules.orchestration.application.ports import (
    WorkflowAgentPort,
    WorkflowRunContext,
    WorkflowToolPort,
)
from qzdap.modules.orchestration.domain.entities import Workflow

TENANT = UUID("00000000-0000-0000-0000-000000000001")
WORKSPACE = UUID("00000000-0000-0000-0000-000000000002")
USER = UUID("00000000-0000-0000-0000-000000000010")


class _ToolPort(WorkflowToolPort):
    def __init__(self, result: dict[str, Any] | None = None) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self._result = result if result is not None else {"rows": [1, 2, 3]}

    async def invoke(
        self,
        *,
        tool_name: str,
        arguments: dict[str, Any],
        context: WorkflowRunContext,
    ) -> dict[str, Any]:
        _ = context
        self.calls.append((tool_name, arguments))
        return dict(self._result)


class _AgentPort(WorkflowAgentPort):
    def __init__(self, reply: str = "已生成周报") -> None:
        self.prompts: list[str] = []
        self._reply = reply

    async def run(self, *, agent: str, prompt: str, context: WorkflowRunContext) -> str:
        _ = (agent, context)
        self.prompts.append(prompt)
        return self._reply


def _context() -> WorkflowRunContext:
    return WorkflowRunContext(
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        user_id=USER,
        workflow_id=uuid4(),
        workflow_name="测试工作流",
    )


def _flow(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> Workflow:
    return Workflow.create(
        id=uuid4(),
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        name="测试工作流",
        description="",
        owner="测试",
        scene="测试",
        trigger="手动触发",
        initial_nodes=nodes,
        initial_edges=edges,
    )


def _node(node_id: str, kind: str, **kwargs: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "label": kwargs.pop("label", node_id),
        "kind": kind,
        "config": kwargs.pop("config", {}),
    }
    data.update(kwargs)
    return {"id": node_id, "type": "flowNode", "data": data}


@pytest.mark.asyncio
async def test_trigger_tool_end_passes_values_downstream() -> None:
    """⚠️ **变量按名字往下传** ✓（Dify 风格 ✓ —— 输入名 = 上游输出名 ✓）。"""
    tools = _ToolPort({"rows": [1, 2, 3]})
    flow = _flow(
        [
            _node(
                "n-trigger",
                "trigger",
                outputs=[{"name": "params"}, {"name": "fired_at"}],
            ),
            _node(
                "n-tool",
                "tool",
                config={"tool": "postgres_query"},
                inputs=[{"name": "params", "required": True}],
                outputs=[{"name": "rows"}],
            ),
            _node(
                "n-end",
                "end",
                config={"action": "return"},
                inputs=[{"name": "rows", "required": True}],
            ),
        ],
        [
            {"source": "n-trigger", "target": "n-tool"},
            {"source": "n-tool", "target": "n-end"},
        ],
    )

    result = await WorkflowEngine(tools=tools).run(
        workflow=flow, context=_context(), inputs={"query": "本周"}
    )

    assert result.ok is True
    assert len(result.steps) == 3
    assert tools.calls[0][0] == "postgres_query"
    assert result.outputs["rows"] == [1, 2, 3]
    assert "rows" in result.summary


@pytest.mark.asyncio
async def test_a_condition_picks_the_branch() -> None:
    """⚠️ **条件节点按判定选分支** ✓（``sourceHandle`` = 出口名 ✓）。"""
    tools = _ToolPort({"score": 5})
    flow = _flow(
        [
            _node("n-trigger", "trigger", outputs=[{"name": "params"}]),
            _node(
                "n-tool",
                "tool",
                config={"tool": "score"},
                inputs=[{"name": "params"}],
                outputs=[{"name": "score"}],
            ),
            _node(
                "n-cond",
                "condition",
                config={"mode": "if", "op": ">=", "value": "3"},
                inputs=[{"name": "score"}],
                outputs=[{"name": "high"}, {"name": "low"}],
            ),
            _node(
                "n-high",
                "end",
                config={"action": "return"},
                inputs=[{"name": "branch"}],
            ),
            _node(
                "n-low",
                "end",
                config={"action": "return"},
                inputs=[{"name": "branch"}],
            ),
        ],
        [
            {"source": "n-trigger", "target": "n-tool"},
            {"source": "n-tool", "target": "n-cond"},
            {"source": "n-cond", "target": "n-high", "sourceHandle": "high"},
            {"source": "n-cond", "target": "n-low", "sourceHandle": "low"},
        ],
    )

    result = await WorkflowEngine(tools=tools).run(workflow=flow, context=_context())

    assert result.ok is True
    node_ids = [step.node_id for step in result.steps]
    assert node_ids == ["n-trigger", "n-tool", "n-cond", "n-high"]
    assert "n-low" not in node_ids


@pytest.mark.asyncio
async def test_an_agent_node_runs_a_turn() -> None:
    """⚠️ **智能体节点真跑一轮** ✓ —— 输入拼成提示 ✓。"""
    agents = _AgentPort("这是一份周报")
    flow = _flow(
        [
            _node("n-trigger", "trigger", outputs=[{"name": "params"}]),
            _node(
                "n-agent",
                "agent",
                config={"agent": "report-writer"},
                inputs=[{"name": "params"}],
                outputs=[{"name": "reply"}],
            ),
            _node(
                "n-end",
                "end",
                config={"action": "return"},
                inputs=[{"name": "reply"}],
            ),
        ],
        [
            {"source": "n-trigger", "target": "n-agent"},
            {"source": "n-agent", "target": "n-end"},
        ],
    )

    result = await WorkflowEngine(agents=agents).run(
        workflow=flow, context=_context(), inputs={"topic": "本周"}
    )

    assert result.ok is True
    assert agents.prompts == ['{"topic": "本周"}']
    assert result.outputs["reply"] == "这是一份周报"


@pytest.mark.asyncio
async def test_a_tool_node_without_a_port_fails_loudly() -> None:
    """⚠️ **没端口就不执行** ✓ —— 明确失败 ✓（不假装跑过 ✗✗）。"""
    flow = _flow(
        [
            _node("n-trigger", "trigger"),
            _node("n-tool", "tool", config={"tool": "postgres_query"}),
        ],
        [{"source": "n-trigger", "target": "n-tool"}],
    )

    result = await WorkflowEngine().run(workflow=flow, context=_context())

    assert result.ok is False
    assert "工具" in result.error
    assert result.steps[-1].ok is False


@pytest.mark.asyncio
async def test_a_failing_node_stops_the_run() -> None:
    """⚠️ **节点失败就停** ✓ —— 结果里写清楚停在哪一步 ✓。"""

    class _BoomTool(WorkflowToolPort):
        async def invoke(self, *, tool_name, arguments, context):  # type: ignore[no-untyped-def]
            _ = (tool_name, arguments, context)
            raise RuntimeError("工具炸了")

    flow = _flow(
        [
            _node("n-trigger", "trigger"),
            _node("n-tool", "tool", config={"tool": "boom"}),
            _node("n-end", "end"),
        ],
        [
            {"source": "n-trigger", "target": "n-tool"},
            {"source": "n-tool", "target": "n-end"},
        ],
    )

    result = await WorkflowEngine(tools=_BoomTool()).run(workflow=flow, context=_context())

    assert result.ok is False
    assert "工具炸了" in result.error
    assert [step.node_id for step in result.steps] == ["n-trigger", "n-tool"]


@pytest.mark.asyncio
async def test_a_cycle_does_not_hang() -> None:
    """⚠️ **图里有环也要停下来** ✓（步数上限 ✓）。"""
    flow = _flow(
        [
            _node("n-trigger", "trigger"),
            _node("n-tool", "tool", config={"tool": "loop"}),
        ],
        [
            {"source": "n-trigger", "target": "n-tool"},
            {"source": "n-tool", "target": "n-tool"},
        ],
    )

    result = await WorkflowEngine(tools=_ToolPort(), max_steps=5).run(
        workflow=flow, context=_context()
    )

    assert result.ok is False
    assert result.error == "TOO_MANY_STEPS"
