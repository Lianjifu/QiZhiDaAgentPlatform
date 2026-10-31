"""Agent Stage 4：专家装配 ✓（选专家 → 取模型 → 取工具 → 留痕载荷 ✓）。

依据：Agent 方案 §4.2（专家实例 = 模型 + 指令 + 工具集 ✓）、§5.2.1（取值链 ✓）、
§5.3.1（绑定集 + 治理过滤 ✓）、A-24（留痕 ✓）。
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest
from langchain_core.tools import BaseTool

from qzdap_agent_runtime.agent_loop.expert import (
    ExpertAssembler,
    decision_payload,
)
from qzdap_agent_runtime.agent_router.classifier import TaskKind
from qzdap_agent_runtime.ports import (
    ActorContext,
    AgentSelection,
    ToolBinding,
    ToolInvocation,
    ToolInvocationResult,
)

TENANT = uuid4()
WORKSPACE = uuid4()
SESSION_AGENT = uuid4()
EXPERT = uuid4()

_ACTOR = ActorContext(actor_id="user-1", tenant_id=str(TENANT), workspace_id=str(WORKSPACE))


class _Router:
    def __init__(self, selection: AgentSelection) -> None:
        self._selection = selection
        self.calls: list[dict[str, Any]] = []

    async def select(self, **kwargs: Any) -> AgentSelection:
        self.calls.append(kwargs)
        return self._selection


class _Bindings:
    def __init__(self, bindings: list[ToolBinding]) -> None:
        self._bindings = bindings
        self.calls: list[dict[str, Any]] = []

    async def bindings(self, **kwargs: Any) -> list[ToolBinding]:
        self.calls.append(kwargs)
        return self._bindings


class _Resolver:
    def __init__(self, model_id: Any) -> None:
        self._model_id = model_id

    async def resolve(self, **kwargs: Any) -> Any:
        return self._model_id


class _LLM:
    async def stream(self, request: Any, **kwargs: Any) -> Any:  # pragma: no cover
        raise NotImplementedError
        yield


class _Runtime:
    def __init__(self) -> None:
        self.calls: list[ToolInvocation] = []

    async def invoke(
        self, invocation: ToolInvocation, *, actor: ActorContext
    ) -> ToolInvocationResult:
        self.calls.append(invocation)
        return ToolInvocationResult(ok=True, output="done")


class TestExpertAssembler:
    @pytest.mark.asyncio
    async def test_the_expert_becomes_a_model_and_a_tool_set(self) -> None:
        """**专家实例 = 模型 + 指令 + 工具集** ✓（§4.2 规则 1 ✓）。"""
        selection = AgentSelection(
            agent_id=EXPERT,
            agent_version="v2",
            task_kind=TaskKind.DEEP_RESEARCH,
            confidence=0.8,
            instruction="你是研究助手",
            model_name="deepseek-chat",
        )
        bindings = _Bindings(
            [
                ToolBinding(name="web_search", kind="tool", risk="medium"),
                ToolBinding(name="echo", kind="tool", risk="low"),
            ]
        )
        assembler = ExpertAssembler(
            router=_Router(selection),  # type: ignore[arg-type]
            bindings=bindings,  # type: ignore[arg-type]
            llm=_LLM(),  # type: ignore[arg-type]
            resolver=_Resolver(None),  # type: ignore[arg-type]
        )
        expert = await assembler.assemble(
            tenant_id=TENANT,
            workspace_id=WORKSPACE,
            session_agent_id=SESSION_AGENT,
            task_kind=TaskKind.DEEP_RESEARCH,
            confidence=0.8,
            actor=_ACTOR,
        )
        assert expert.selection.agent_id == EXPERT
        assert expert.instruction == "你是研究助手"
        assert expert.model.model_name == "deepseek-chat"
        assert [tool.name for tool in expert.tools] == ["web_search", "echo"]
        assert all(isinstance(tool, BaseTool) for tool in expert.tools)

    @pytest.mark.asyncio
    async def test_the_model_id_is_resolved_by_name(self) -> None:
        """**模型名 → 查表 → 模型 id** ✓（§5.2.1 ✓ —— 查表不是决策 ✓）。"""
        from qzdap_schema.ids import ModelId

        resolved = ModelId(uuid4())
        selection = AgentSelection(
            agent_id=EXPERT,
            agent_version="v1",
            task_kind=TaskKind.SIMPLE_QA,
            confidence=0.9,
            model_name="deepseek-chat",
        )
        assembler = ExpertAssembler(
            router=_Router(selection),  # type: ignore[arg-type]
            bindings=_Bindings([]),  # type: ignore[arg-type]
            llm=_LLM(),  # type: ignore[arg-type]
            resolver=_Resolver(resolved),  # type: ignore[arg-type]
        )
        expert = await assembler.assemble(
            tenant_id=TENANT,
            workspace_id=WORKSPACE,
            session_agent_id=SESSION_AGENT,
            task_kind=TaskKind.SIMPLE_QA,
            confidence=0.9,
        )
        assert expert.model.model_id == resolved

    @pytest.mark.asyncio
    async def test_the_unprotected_turn_drops_the_side_effect_tools(self) -> None:
        """**未受保护的轮次看不到副作用工具** ✓（§5.3.1 规则 3 ✓）。"""
        selection = AgentSelection(
            agent_id=EXPERT,
            agent_version="v1",
            task_kind=TaskKind.SIMPLE_QA,
            confidence=0.9,
            model_name="demo",
        )
        bindings = _Bindings(
            [
                ToolBinding(name="echo", kind="tool", risk="low"),
                ToolBinding(name="write_file", kind="tool", risk="high", side_effect=True),
            ]
        )
        assembler = ExpertAssembler(
            router=_Router(selection),  # type: ignore[arg-type]
            bindings=bindings,  # type: ignore[arg-type]
            llm=_LLM(),  # type: ignore[arg-type]
        )
        expert = await assembler.assemble(
            tenant_id=TENANT,
            workspace_id=WORKSPACE,
            session_agent_id=SESSION_AGENT,
            task_kind=TaskKind.SIMPLE_QA,
            confidence=0.9,
            protected=False,
        )
        assert [tool.name for tool in expert.tools] == ["echo"]

    @pytest.mark.asyncio
    async def test_the_binding_set_is_read_for_the_selected_expert(self) -> None:
        """**绑定集按选中的专家取** ✓（§5.3.1 规则 6 ✓）。"""
        selection = AgentSelection(
            agent_id=EXPERT,
            agent_version="v3",
            task_kind=TaskKind.SIMPLE_QA,
            confidence=0.9,
            model_name="demo",
        )
        bindings = _Bindings([])
        assembler = ExpertAssembler(
            router=_Router(selection),  # type: ignore[arg-type]
            bindings=bindings,  # type: ignore[arg-type]
            llm=_LLM(),  # type: ignore[arg-type]
        )
        await assembler.assemble(
            tenant_id=TENANT,
            workspace_id=WORKSPACE,
            session_agent_id=SESSION_AGENT,
            task_kind=TaskKind.SIMPLE_QA,
            confidence=0.9,
        )
        assert bindings.calls[0]["agent_id"] == EXPERT
        assert bindings.calls[0]["agent_version"] == "v3"


class TestDecisionPayload:
    def test_it_records_what_was_used(self) -> None:
        """**记「用了什么」** ✓（A-24 ✓）。"""
        from qzdap_agent_runtime.execution.llm_client import ResolvedModel

        selection = AgentSelection(
            agent_id=EXPERT,
            agent_version="v1",
            task_kind=TaskKind.SIMPLE_QA,
            confidence=0.9,
            model_name="demo",
        )
        payload = decision_payload(
            selection=selection,
            resolved=ResolvedModel(model_name="demo"),
            tool_names=("echo",),
        )
        assert payload["expert_agent_id"] == str(EXPERT)
        assert payload["task_kind"] == "SIMPLE_QA"
        assert payload["model"]["name"] == "demo"
        assert payload["tools"] == ["echo"]
        assert "route_decision" not in payload, "那是 Router 层的列"
        assert "reason" not in payload, "只记用了什么，不记为什么"


__all__ = ["UUID"]
