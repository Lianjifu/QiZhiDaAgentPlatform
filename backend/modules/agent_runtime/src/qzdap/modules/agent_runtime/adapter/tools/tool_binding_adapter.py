"""``ToolBindingAdapter`` —— **取 agent 配置的绑定集** ✓（Agent 方案 §5.3.1 ✓）。

依据：Agent 方案 §5.3.1（绑定集读取与治理过滤 ✓ —— **不是选择** ✓）、
§8.1（``execution/tool_binding.py`` ✓ —— runtime 侧 ✓）、§9 Stage 2
（修 ``list_tools`` 的空 schema ✓ —— 真实 schema 从 ``tools`` 表的 spec 长出来 ✓）。

⚠️ **本模块只「取」** ✓ —— 治理过滤（风险 ∩ 作用域 ∩ 副作用 ✓）在 Execution
那一侧做 ✓（端口不重复那份规则 ✗✗ —— 那是**两套实现** ✗✗✗）。

⚠️ **三种来源统一成一种形状** ✓ —— tool / mcp / skill → ``ToolBinding`` ✓
（§5.3.1 规则 5 ✓ —— 对模型是同一种东西 ✓）。

⚠️ **绑定集为空不是错误** ✓（规则 1 ✓）—— 返回空列表 ✓。
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from qzdap.modules.agent_runtime.application.ports import (
    AgentBindingReader,
    SkillPort,
    ToolPort,
)
from qzdap_agent_runtime.ports import ToolBinding, ToolBindingPort

#: **skill 的 inputSchema → JSON Schema** ✓（skill 那边是一张**字段表** ✓，
#: 不是 JSON Schema ✓ —— 这里转一下 ✓）。
_JSON_TYPES = {
    "string": "string",
    "number": "number",
    "integer": "integer",
    "boolean": "boolean",
    "array": "array",
    "object": "object",
}

#: **沙箱工具的绑定声明** ✓（旧路径里它是**固定提供**的 ✓ —— 高风险 ✓
#: **必须审批** ✓ —— 不审批就等于让模型直接跑代码 ✗✗）。
_SANDBOX_BINDING = ToolBinding(
    name="sandbox_exec",
    kind="tool",
    risk="high",
    requires_approval=True,
    side_effect=True,
    spec={
        "description": "在沙箱里执行一段代码",
        "parameters": {
            "type": "object",
            "properties": {
                "language": {"type": "string"},
                "code": {"type": "string"},
                "timeout_ms": {"type": "integer"},
            },
        },
    },
)


class ToolBindingAdapter(ToolBindingPort):
    """**绑定集 → ``ToolBinding`` 列表** ✓。

    ⚠️ **只取不选** ✓ —— 绑定集是 agent 配置里声明的 ✓（§5.3.1 ✓）。
    """

    def __init__(
        self,
        *,
        tools: ToolPort | None = None,
        skills: SkillPort | None = None,
        agents: AgentBindingReader | None = None,
        sandbox: bool = False,
    ) -> None:
        self._tools = tools
        self._skills = skills
        self._agents = agents
        self._sandbox = sandbox

    async def bindings(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        agent_id: UUID,
        agent_version: str,
    ) -> list[ToolBinding]:
        """**取绑定集** ✓ —— 空就是空 ✓（不是错误 ✓）。

        ⚠️ **agent 没钉工具时的口径** ✓（与旧路径一致 ✓）—— **给出全部可执行
        skill** ✓，**不给目录工具** ✓（否则每个 agent 都凭空多出网络 / 文件
        系统的能力 ✗✗）。
        """
        _ = (tenant_id, workspace_id, agent_version)
        names: tuple[str, ...] = ()
        if self._agents is not None:
            names = await self._agents.declared(
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                agent_id=agent_id,
                agent_version=agent_version,
            )
        catalog = await self._tool_catalog()
        skills = await self._skill_catalog()
        if not names:
            names = tuple(skills)

        bindings: list[ToolBinding] = []
        for name in names:
            if name in skills:
                bindings.append(_skill_binding(name, skills[name]))
                continue
            entry = catalog.get(name)
            if entry is None:
                # ⚠️ **没注册的工具不暴露** ✓ —— 暴露了模型就会去调一个不存在
                # 的东西 ✗✗（调用时才失败 ✗）。
                continue
            bindings.append(_tool_binding(name, entry))
        if self._sandbox:
            bindings.append(_SANDBOX_BINDING)
        return bindings

    async def _tool_catalog(self) -> dict[str, dict[str, Any]]:
        if self._tools is None:
            return {}
        try:
            rows = await self._tools.list_tools()
        except Exception:
            return {}
        return {str(row.get("name")): row for row in rows if row.get("name")}

    async def _skill_catalog(self) -> dict[str, dict[str, Any]]:
        if self._skills is None:
            return {}
        try:
            rows = await self._skills.list_executable()
        except Exception:
            return {}
        return {str(row.get("name")): row for row in rows if row.get("name")}


def _tool_binding(name: str, entry: dict[str, Any]) -> ToolBinding:
    """**工具目录条目 → 绑定声明** ✓（含**真实参数契约** ✓）。"""
    risk = str(entry.get("risk") or "low")
    if risk not in {"low", "medium", "high"}:
        risk = "low"
    needs_confirm = bool(entry.get("needConfirm", False))
    protocol = str(entry.get("protocol") or "")
    spec: dict[str, Any] = {
        "description": str(entry.get("description") or name),
        "parameters": entry.get("parameters") or {"type": "object", "properties": {}},
    }
    if protocol:
        spec["protocol"] = protocol
    return ToolBinding(
        name=name,
        kind="mcp" if protocol == "mcp" else "tool",
        risk=risk,  # type: ignore[arg-type]
        # ⚠️ **要审批 = 声明要审批 或 风险不是 low** ✓（旧路径 `needs_confirm`
        # 的口径 ✓ —— 高风险的工具**等审批** ✓ 而不是被悄悄放行 ✓）。
        requires_approval=needs_confirm or risk != "low",
        # ⚠️ **副作用 = 要审批或高风险** ✓（未受保护的轮次要剔除它们 ✓）。
        side_effect=bool(entry.get("side_effect", needs_confirm or risk == "high")),
        spec=spec,
    )


def _skill_binding(name: str, entry: dict[str, Any]) -> ToolBinding:
    """**skill 条目 → 绑定声明** ✓（对模型与工具是同一种东西 ✓）。"""
    risk = str(entry.get("risk") or "low")
    if risk not in {"low", "medium", "high"}:
        risk = "low"
    needs_confirm = bool(entry.get("needConfirm", False))
    return ToolBinding(
        name=name,
        kind="skill",
        risk=risk,  # type: ignore[arg-type]
        requires_approval=needs_confirm or risk != "low",
        side_effect=bool(entry.get("side_effect", needs_confirm or risk == "high")),
        spec={
            "description": str(entry.get("description") or name),
            "parameters": _skill_parameters(entry.get("inputSchema")),
        },
    )


def _skill_parameters(input_schema: Any) -> dict[str, Any]:
    """**skill 的字段表 → JSON Schema** ✓（skill 那边存的是一张表 ✓）。"""
    if isinstance(input_schema, dict) and input_schema:
        return input_schema
    properties: dict[str, Any] = {}
    required: list[str] = []
    for field in input_schema or []:
        if not isinstance(field, dict):
            continue
        name = str(field.get("name") or "")
        if not name:
            continue
        properties[name] = {
            "type": _JSON_TYPES.get(str(field.get("type") or "string"), "string"),
            **({"description": str(field["description"])} if field.get("description") else {}),
        }
        if field.get("required"):
            required.append(name)
    schema: dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required
    return schema


__all__ = ["ToolBindingAdapter"]
