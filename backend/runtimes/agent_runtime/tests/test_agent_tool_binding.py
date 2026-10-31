"""Agent Stage 2：工具绑定与治理过滤。

依据：Agent 方案 §5.3.1（绑定集读取与治理过滤 ✓ —— 「不是选择」✓）、
§9 Stage 2（验收四条 ✓）。

验收四条：**取不到 actor → 拒绝执行工具** ✓ / **`unprotected` 轮次不产生
任何副作用工具调用** ✓ / **绑定集为空不是错误** ✓ / **tool / mcp / skill
统一成 `BaseTool`** ✓。
"""

from __future__ import annotations

import pytest
from langchain_core.tools import BaseTool

from qzdap_agent_runtime.execution import (
    BindingPolicy,
    ToolBindingResolver,
    current_actor,
    require_actor,
    reset_current_actor,
    set_current_actor,
    tool_schema,
)
from qzdap_agent_runtime.ports import (
    ActorContext,
    ToolBinding,
    ToolInvocation,
    ToolInvocationResult,
)

ACTOR = ActorContext(
    actor_id="user-1",
    tenant_id="tenant-1",
    workspace_id="workspace-1",
)


class _RecordingRuntime:
    """工具运行时端口的替身 ✓。"""

    def __init__(self, *, ok: bool = True, output: str = "done") -> None:
        self._ok = ok
        self._output = output
        self.calls: list[tuple[ToolInvocation, ActorContext]] = []

    async def invoke(
        self, invocation: ToolInvocation, *, actor: ActorContext
    ) -> ToolInvocationResult:
        self.calls.append((invocation, actor))
        if not self._ok:
            return ToolInvocationResult(ok=False, error_code="TOOL_FAILED")
        return ToolInvocationResult(ok=True, output=self._output)


def _binding(**kwargs) -> ToolBinding:
    defaults = {
        "name": "echo",
        "kind": "tool",
        "risk": "low",
        "side_effect": False,
        "spec": {
            "description": "回显",
            "parameters": {"type": "object", "properties": {"text": {"type": "string"}}},
        },
    }
    defaults.update(kwargs)
    return ToolBinding(**defaults)


class TestUnification:
    """§5.3.1 规则 5 ✓ —— **三种来源对模型是同一种东西** ✓。"""

    def test_tool_mcp_and_skill_all_become_base_tools(self) -> None:
        resolver = ToolBindingResolver()
        tools = resolver.resolve(
            [
                _binding(name="echo", kind="tool"),
                _binding(name="remote", kind="mcp"),
                _binding(name="summarize", kind="skill"),
            ]
        )
        assert [tool.name for tool in tools] == ["echo", "remote", "summarize"]
        assert all(isinstance(tool, BaseTool) for tool in tools)

    def test_the_spec_becomes_the_argument_schema(self) -> None:
        """**spec 的真实参数进 schema** ✓ —— 不是空壳 ✓。"""
        resolver = ToolBindingResolver()
        tools = resolver.resolve(
            [
                _binding(
                    spec={
                        "description": "搜一下",
                        "parameters": {
                            "type": "object",
                            "properties": {"query": {"type": "string"}},
                            "required": ["query"],
                        },
                    }
                )
            ]
        )
        schema = tool_schema(tools[0])
        assert schema["function"]["name"] == "echo"
        assert "query" in schema["function"]["parameters"]["properties"]

    def test_the_properties_fallback_is_used(self) -> None:
        resolver = ToolBindingResolver()
        tools = resolver.resolve(
            [
                _binding(
                    spec={
                        "description": "带 properties 的 spec",
                        "properties": {"path": {"type": "string"}},
                        "required": ["path"],
                    }
                )
            ]
        )
        parameters = tool_schema(tools[0])["function"]["parameters"]
        assert parameters["properties"] == {"path": {"type": "string"}}
        assert parameters["required"] == ["path"]


class TestGovernance:
    """§5.3.1 的六条治理规则 ✓。"""

    def test_an_empty_binding_set_is_not_an_error(self) -> None:
        """规则 1 ✓ —— 本步就是纯对话 ✓。"""
        assert ToolBindingResolver().resolve([]) == []

    def test_the_side_effect_tools_are_removed_for_unprotected_turns(self) -> None:
        """规则 3 ✓ —— **剔除，不是执行时拦截** ✓。

        ⚠️ 未受保护的轮次**根本不该看见**副作用工具 ✓（看见了就会想去调 ✓）。
        """
        resolver = ToolBindingResolver()
        bindings = [
            _binding(name="echo"),
            _binding(name="write_file", risk="high", side_effect=True),
        ]
        tools = resolver.resolve(bindings, policy=BindingPolicy(unprotected=True))
        assert [tool.name for tool in tools] == ["echo"]

    def test_the_high_risk_tools_are_not_filtered_out(self) -> None:
        """规则 4 ✓ —— **筛不等于批** ✓（高风险交给 `PolicyGuard` 判 ✓）。"""
        resolver = ToolBindingResolver()
        tools = resolver.resolve([_binding(name="bash", risk="high", side_effect=True)])
        assert [tool.name for tool in tools] == ["bash"]

    def test_the_risk_policy_filters_the_bindings(self) -> None:
        resolver = ToolBindingResolver()
        tools = resolver.resolve(
            [
                _binding(name="echo"),
                _binding(name="web_search", risk="medium"),
                _binding(name="bash", risk="high"),
            ],
            policy=BindingPolicy(allowed_risks=frozenset({"low", "medium"})),
        )
        assert [tool.name for tool in tools] == ["echo", "web_search"]


class TestActor:
    """**取不到 actor → 拒绝执行工具** ✓。"""

    @pytest.mark.asyncio
    async def test_the_tool_is_not_executed_without_an_actor(self) -> None:
        runtime = _RecordingRuntime()
        tools = ToolBindingResolver(runtime).resolve([_binding()])
        with pytest.raises(Exception, match="actor"):
            await tools[0].ainvoke({"text": "hi"})
        assert runtime.calls == [], "没有真实调用者就不许执行工具"

    @pytest.mark.asyncio
    async def test_the_real_actor_reaches_the_runtime(self) -> None:
        runtime = _RecordingRuntime(output="回显: hi")
        tools = ToolBindingResolver(runtime).resolve([_binding()])
        token = set_current_actor(ACTOR)
        try:
            result = await tools[0].ainvoke({"text": "hi"})
        finally:
            reset_current_actor(token)
        assert result == "回显: hi"
        assert runtime.calls[0][1] is ACTOR
        assert runtime.calls[0][0].arguments == {"text": "hi"}

    @pytest.mark.asyncio
    async def test_a_failing_tool_raises_with_the_error_code(self) -> None:
        runtime = _RecordingRuntime(ok=False)
        tools = ToolBindingResolver(runtime).resolve([_binding()])
        token = set_current_actor(ACTOR)
        try:
            with pytest.raises(Exception, match="TOOL_FAILED"):
                await tools[0].ainvoke({"text": "hi"})
        finally:
            reset_current_actor(token)

    def test_the_actor_context_is_required(self) -> None:
        with pytest.raises(RuntimeError):
            require_actor(None)
        assert require_actor(ACTOR) is ACTOR

    def test_the_actor_is_read_from_the_context(self) -> None:
        token = set_current_actor(ACTOR)
        try:
            assert current_actor() is ACTOR
        finally:
            reset_current_actor(token)
        with pytest.raises(RuntimeError):
            current_actor()
