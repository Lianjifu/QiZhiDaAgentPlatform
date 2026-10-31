"""**工作流执行引擎** ✓ —— 真的走一遍图 ✓。

⚠️ **之前只有「记一条使用记录」** ✓（`record_run` ✓）—— 那不是执行 ✗✗
（跑完什么也没发生 ✓ —— 却显示成「已执行」✓ —— theater ✗）。

⚠️ **引擎只做编排** ✓ —— 工具节点真调工具 ✓（`WorkflowToolPort` ✓），
智能体节点真跑一轮对话 ✓（`WorkflowAgentPort` ✓）—— **这两个口没接就不
执行那类节点** ✓（而不是编结果 ✗✗）。

**图的形状** ✓（前端 reactflow 的节点 / 边 ✓）：

- 节点：``{"id", "data": {"kind", "label", "config", "inputs", "outputs"}}`` ✓；
  五种 kind ✓：``trigger`` ✓ / ``tool`` ✓ / ``agent`` ✓ / ``condition`` ✓ /
  ``end`` ✓；
- 边：``{"source", "target"}`` ✓ —— 条件分支用 ``sourceHandle`` 标出口名 ✓
  （reactflow 的约定 ✓）。

**变量怎么传** ✓ —— Dify 风格 ✓：**下游节点的输入名 = 上游节点的输出名**
✓（``data.inputs[].name`` ✓）→ 引擎按名字在「变量袋」里找 ✓。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from qzdap.modules.orchestration.application.ports import (
    WorkflowAgentPort,
    WorkflowRunContext,
    WorkflowToolPort,
)
from qzdap.modules.orchestration.domain.entities import Workflow

#: 一轮最多走多少个节点 ✓ —— 防「图里有环」把进程跑死 ✓。
MAX_STEPS = 20


@dataclass(frozen=True, slots=True)
class NodeOutcome:
    """**一个节点跑完的样子** ✓。"""

    node_id: str
    kind: str
    label: str
    ok: bool
    outputs: dict[str, Any] = field(default_factory=dict)
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "nodeId": self.node_id,
            "kind": self.kind,
            "label": self.label,
            "ok": self.ok,
            "outputs": _plain(self.outputs),
            "error": self.error,
        }


@dataclass(frozen=True, slots=True)
class WorkflowRunResult:
    """**一次运行的结论** ✓。"""

    ok: bool
    steps: tuple[NodeOutcome, ...] = ()
    outputs: dict[str, Any] = field(default_factory=dict)
    summary: str = ""
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "steps": [step.to_dict() for step in self.steps],
            "outputs": _plain(self.outputs),
            "summary": self.summary,
            "error": self.error,
        }


class WorkflowEngine:
    """**按图走一遍** ✓ —— 真的执行 ✓。"""

    def __init__(
        self,
        *,
        tools: WorkflowToolPort | None = None,
        agents: WorkflowAgentPort | None = None,
        max_steps: int = MAX_STEPS,
    ) -> None:
        self._tools = tools
        self._agents = agents
        self._max_steps = max(1, int(max_steps))

    async def run(
        self,
        *,
        workflow: Workflow,
        context: WorkflowRunContext,
        inputs: dict[str, Any] | None = None,
    ) -> WorkflowRunResult:
        """跑一遍这张图 ✓ —— 返回每一步 + 结论 ✓。

        ⚠️ **节点失败就停** ✓ —— 跑不完的图**不算跑完** ✓（结果里写清楚
        停在哪一步 ✓）。
        """
        nodes = {
            str(item.get("id") or ""): item
            for item in workflow.initial_nodes
            if isinstance(item, dict) and item.get("id")
        }
        edges = [item for item in workflow.initial_edges if isinstance(item, dict)]
        start = _find_start(nodes)
        if start is None:
            return WorkflowRunResult(
                ok=False, summary="工作流没有入口节点", error="NO_TRIGGER_NODE"
            )

        bag: dict[str, Any] = {}
        steps: list[NodeOutcome] = []
        current: dict[str, Any] | None = start
        visited = 0

        while current is not None:
            if visited >= self._max_steps:
                return WorkflowRunResult(
                    ok=False,
                    steps=tuple(steps),
                    summary=f"执行超过 {self._max_steps} 步仍未结束",
                    error="TOO_MANY_STEPS",
                )
            visited += 1
            node_id = str(current.get("id"))
            data = _dict_field(current, "data")
            kind = str(data.get("kind") or "")
            label = str(data.get("label") or node_id)
            config = _dict_field(data, "config")
            node_inputs = _collect_inputs(data, bag, inputs or {})

            try:
                outputs = await self._execute(
                    kind=kind,
                    config=config,
                    data=data,
                    node_inputs=node_inputs,
                    context=context,
                    workflow=workflow,
                )
            except Exception as exc:
                message = str(exc) or type(exc).__name__
                steps.append(
                    NodeOutcome(node_id=node_id, kind=kind, label=label, ok=False, error=message)
                )
                return WorkflowRunResult(
                    ok=False,
                    steps=tuple(steps),
                    summary=f"「{label}」执行失败：{message}",
                    error=message,
                )

            steps.append(
                NodeOutcome(node_id=node_id, kind=kind, label=label, ok=True, outputs=outputs)
            )
            for name, value in outputs.items():
                bag[f"{node_id}.{name}"] = value

            if kind == "end":
                action = str(config.get("action") or "done")
                summary = _end_summary(action, config, node_inputs)
                return WorkflowRunResult(
                    ok=True, steps=tuple(steps), outputs=node_inputs, summary=summary
                )

            current = _next_node(nodes, edges, current, outputs)

        return WorkflowRunResult(
            ok=False,
            steps=tuple(steps),
            summary="工作流没有走到结束节点",
            error="NO_END_NODE",
        )

    async def _execute(
        self,
        *,
        kind: str,
        config: dict[str, Any],
        data: dict[str, Any],
        node_inputs: dict[str, Any],
        context: WorkflowRunContext,
        workflow: Workflow,
    ) -> dict[str, Any]:
        """**跑一个节点** ✓ —— 按 kind 分派 ✓。"""
        if kind == "trigger":
            fired_at = datetime.now(UTC).isoformat()
            return {
                "params": node_inputs,
                "fired_at": fired_at,
                "workflow": workflow.name,
            }
        if kind == "tool":
            tool_name = str(config.get("tool") or "").strip()
            if not tool_name:
                raise ValueError("工具节点没有配置工具名")
            if self._tools is None:
                raise RuntimeError("没有接工具执行口 —— 工具节点无法执行")
            result = await self._tools.invoke(
                tool_name=tool_name, arguments=node_inputs, context=context
            )
            return _map_outputs(result)
        if kind == "agent":
            agent = str(config.get("agent") or "").strip()
            if not agent:
                raise ValueError("智能体节点没有配置智能体")
            if self._agents is None:
                raise RuntimeError("没有接智能体执行口 —— 智能体节点无法执行")
            prompt = _as_prompt(node_inputs)
            reply = await self._agents.run(agent=agent, prompt=prompt, context=context)
            return {"reply": reply, "output": reply}
        if kind == "condition":
            branch = _evaluate_condition(config, data, node_inputs)
            return {"branch": branch, "result": branch}
        if kind == "end":
            return dict(node_inputs)
        raise ValueError(f"不支持的节点类型：{kind or '未标注'}")


def _dict_field(data: dict[str, Any], key: str) -> dict[str, Any]:
    """**取一个字典字段** ✓ —— 不是字典就当没有 ✓（不猜 ✓）。"""
    value = data.get(key)
    return value if isinstance(value, dict) else {}


def _find_start(nodes: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    """**入口节点** ✓ —— 第一个 ``trigger`` ✓。"""
    for node in nodes.values():
        data = _dict_field(node, "data")
        if str(data.get("kind") or "") == "trigger":
            return node
    return None


def _collect_inputs(
    data: dict[str, Any], bag: dict[str, Any], fallback: dict[str, Any]
) -> dict[str, Any]:
    """**按名字收输入** ✓（Dify 风格 ✓ —— 输入名 = 上游输出名 ✓）。

    ⚠️ **找不到就留空** ✓ —— 不猜 ✗✗（猜出来的值会让流程「看起来跑通了」
    ✗✗ —— 那比失败更糟 ✓）。
    """
    declared = data.get("inputs")
    if not isinstance(declared, list) or not declared:
        return dict(fallback)
    values: dict[str, Any] = {}
    for item in declared:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        if name in bag:
            values[name] = bag[name]
            continue
        match = next((v for k, v in bag.items() if k.endswith(f".{name}")), None)
        if match is not None:
            values[name] = match
            continue
        if name in fallback:
            values[name] = fallback[name]
    return values


def _next_node(
    nodes: dict[str, dict[str, Any]],
    edges: list[dict[str, Any]],
    current: dict[str, Any],
    outputs: dict[str, Any],
) -> dict[str, Any] | None:
    """**下一个节点** ✓ —— 条件分支按 ``sourceHandle`` 选 ✓。"""
    node_id = str(current.get("id"))
    outgoing = [edge for edge in edges if str(edge.get("source") or "") == node_id]
    if not outgoing:
        return None
    branch = str(outputs.get("branch") or "")
    if branch:
        for edge in outgoing:
            if str(edge.get("sourceHandle") or "") == branch:
                return nodes.get(str(edge.get("target") or ""))
    return nodes.get(str(outgoing[0].get("target") or ""))


def _evaluate_condition(
    config: dict[str, Any], data: dict[str, Any], node_inputs: dict[str, Any]
) -> str:
    """**条件判定** ✓ —— 返回**分支名** ✓（= 节点的第一个 / 第二个输出口 ✓）。

    ⚠️ **两种模式** ✓：``if`` ✓（比较 ✓）与 ``switch`` ✓（按值选 ✓）。
    ⚠️ **判不出来就落到第二个出口** ✓（兜底分支 ✓ —— 不猜 ✓）。
    """
    outputs = _declared_outputs(data)
    first = outputs[0] if outputs else "true"
    second = outputs[1] if len(outputs) > 1 else "false"
    value = next(iter(node_inputs.values()), None)
    mode = str(config.get("mode") or "if").lower()
    if mode == "switch":
        text = str(value or "")
        for name in outputs:
            if name == text:
                return name
        return second
    op = str(config.get("op") or "==")
    expected = str(config.get("value") or "")
    return first if _compare(value, op, expected) else second


def _compare(value: Any, op: str, expected: str) -> bool:
    """**比较** ✓ —— 数字优先按数字比 ✓（否则按字符串 ✓）。"""
    try:
        left: Any = float(value)  # type: ignore[arg-type]
        right: Any = float(expected)
    except (TypeError, ValueError):
        left, right = str(value or ""), expected
    if op == ">=":
        return left >= right
    if op == ">":
        return left > right
    if op == "<=":
        return left <= right
    if op == "<":
        return left < right
    if op == "!=":
        return left != right
    return left == right


def _declared_outputs(data: dict[str, Any]) -> list[str]:
    """**节点的输出口名** ✓（``data.outputs[].name`` ✓）—— 分支就按它选 ✓。"""
    declared = data.get("outputs")
    if not isinstance(declared, list):
        return []
    names: list[str] = []
    for item in declared:
        if isinstance(item, dict):
            name = str(item.get("name") or "").strip()
            if name:
                names.append(name)
    return names


def _map_outputs(result: dict[str, Any]) -> dict[str, Any]:
    """**工具结果 → 节点输出** ✓ —— 结果不是字典就整体塞进 ``result`` ✓。"""
    if not isinstance(result, dict):
        return {"result": result}
    if len(result) == 1:
        only = next(iter(result))
        return {only: result[only], "result": result[only]}
    return {**result, "result": result}


def _as_prompt(node_inputs: dict[str, Any]) -> str:
    """**节点的输入 → 一段提示** ✓ —— 拼成文本 ✓（非字符串走 JSON ✓）。"""
    if not node_inputs:
        return ""
    if list(node_inputs) == ["params"]:
        # ⚠️ **触发节点的 params** ✓ —— 直接用它 ✓（不套一层壳 ✓）。
        only = node_inputs["params"]
        if isinstance(only, str):
            return only
        import json

        return json.dumps(only, ensure_ascii=False)
    if len(node_inputs) == 1:
        only = next(iter(node_inputs.values()))
        if isinstance(only, str):
            return only
    import json

    return json.dumps(node_inputs, ensure_ascii=False)


def _end_summary(action: str, config: dict[str, Any], node_inputs: dict[str, Any]) -> str:
    """**结束节点的话** ✓ —— 说清楚这一步到底做了什么 ✓。"""
    if action == "notify":
        target = str(config.get("target") or "").strip()
        return f"已完成，通知目标：{target or '未配置'}"
    if action == "return":
        if not node_inputs:
            return "已完成"
        return "已完成：" + "；".join(f"{k}={_short(v)}" for k, v in node_inputs.items())
    return "执行完成"


def _short(value: Any) -> str:
    text = value if isinstance(value, str) else str(value)
    return text if len(text) <= 60 else text[:57] + "…"


def _plain(value: Any) -> Any:
    """**结果要能进 JSONB** ✓ —— 非 JSON 的值退成字符串 ✓。"""
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return str(value)


__all__ = ["MAX_STEPS", "NodeOutcome", "WorkflowEngine", "WorkflowRunResult"]
