"""Agent Stage 0：契约 —— 五个端口 + ``QZDAPChatModel`` 骨架 ✓。

依据：Agent 方案 §8.1（新增文件 ✓）、§2.2（**为什么必须写适配器** ✓）、
§4.1 / §5.2.1 / §5.3.1（端口语义 ✓）、§9 Stage 0（**验收** ✓）。

验收三条 ✓：**五个端口有契约测试** ✓ / **``QZDAPChatModel`` 是
``BaseChatModel`` 的实例且能被调用** ✓ / **依赖版本对得上** ✓。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage
from qzdap_llm.client import ChatRequest, LLMChunk
from qzdap_schema.ids import ModelId

from qzdap_agent_runtime.agent_router import (
    AgentRouteConfig,
    TaskClassification,
    TaskClassifier,
    TaskKind,
)
from qzdap_agent_runtime.execution import QZDAPChatModel
from qzdap_agent_runtime.ports import (
    ActorContext,
    AgentRouterPort,
    AgentSelection,
    LLMPort,
    ModelResolverPort,
    ToolBinding,
    ToolBindingPort,
    ToolInvocation,
    ToolInvocationResult,
    ToolRuntimePort,
)

# ---------------------------------------------------------------------------
# 五个端口的契约测试
# ---------------------------------------------------------------------------


class _FakeLLM:
    async def stream(
        self,
        request: ChatRequest,
        *,
        model_id: ModelId | None = None,
        route_id: ModelId | None = None,
        fallback_model_ids: list[ModelId] | None = None,
        actor: ActorContext | None = None,
    ) -> AsyncIterator[LLMChunk]:
        yield LLMChunk(model=request.model, delta="ok")


class _EchoLLM:
    """会说一句话的端口替身 ✓。"""

    async def stream(
        self,
        request: ChatRequest,
        *,
        model_id: ModelId | None = None,
        route_id: ModelId | None = None,
        fallback_model_ids: list[ModelId] | None = None,
        actor: ActorContext | None = None,
    ) -> AsyncIterator[LLMChunk]:
        _ = (model_id, route_id, fallback_model_ids, actor)
        yield LLMChunk(model=request.model, delta="你好")


class _FakeResolver:
    async def resolve(
        self,
        *,
        tenant_id: Any,
        workspace_id: Any,
        upstream_model: str,
    ) -> ModelId | None:
        _ = (tenant_id, workspace_id)
        return ModelId(uuid4()) if upstream_model else None


class _FakeBinding:
    async def bindings(
        self,
        *,
        tenant_id: Any,
        workspace_id: Any,
        agent_id: Any,
        agent_version: str,
    ) -> list[ToolBinding]:
        _ = (tenant_id, workspace_id, agent_id, agent_version)
        return [ToolBinding(name="search", kind="tool")]


class _FakeAgentRouter:
    async def select(
        self,
        *,
        tenant_id: Any,
        workspace_id: Any,
        session_agent_id: Any,
        task_kind: TaskKind,
        confidence: float,
        tool_names: tuple[str, ...] = (),
    ) -> AgentSelection:
        _ = (tenant_id, workspace_id, tool_names)
        return AgentSelection(
            agent_id=session_agent_id,
            agent_version="v1",
            task_kind=task_kind,
            confidence=confidence,
        )


class _FakeToolRuntime:
    async def invoke(
        self,
        invocation: ToolInvocation,
        *,
        actor: ActorContext,
    ) -> ToolInvocationResult:
        _ = actor
        return ToolInvocationResult(ok=True, output=invocation.name)


class TestTheFivePorts:
    """**五个端口** ✓（Agent 方案 §8.1 ✓）。"""

    def test_a_conforming_implementation_satisfies_the_port(self) -> None:
        assert isinstance(_FakeLLM(), LLMPort)
        assert isinstance(_FakeResolver(), ModelResolverPort)
        assert isinstance(_FakeBinding(), ToolBindingPort)
        assert isinstance(_FakeAgentRouter(), AgentRouterPort)
        assert isinstance(_FakeToolRuntime(), ToolRuntimePort)

    def test_an_object_without_the_methods_does_not(self) -> None:
        assert not isinstance(object(), LLMPort)
        assert not isinstance(object(), ModelResolverPort)
        assert not isinstance(object(), ToolBindingPort)
        assert not isinstance(object(), AgentRouterPort)
        assert not isinstance(object(), ToolRuntimePort)

    def test_there_is_no_tool_router_port(self) -> None:
        """**没有 `ToolRouterPort`** ✓ —— 决策 #4 取消了「工具路由」✓。

        ⚠️ 「工具路由」这个概念一旦回来，就会有**第二套选工具的逻辑** ✗✗。
        """
        import qzdap_agent_runtime.ports as ports_module

        assert not hasattr(ports_module, "ToolRouterPort")


class TestToolBinding:
    def test_the_default_binding_is_protected_and_harmless(self) -> None:
        binding = ToolBinding(name="search")
        assert binding.protected is True
        assert binding.side_effect is False
        assert binding.risk == "low"


# ---------------------------------------------------------------------------
# QZDAPChatModel（§2.2 · A-02）
# ---------------------------------------------------------------------------


class TestQZDAPChatModel:
    def test_it_is_a_base_chat_model(self) -> None:
        """**必须是 `BaseChatModel` 的实例** ✓（§2.2 的全部意义就在这 ✓）。"""
        model = QZDAPChatModel(llm=_FakeLLM())
        assert isinstance(model, BaseChatModel)

    @pytest.mark.asyncio
    async def test_it_answers_a_message(self) -> None:
        """**能被调用** ✓ —— 这是 LangGraph 节点的 `model` 参数的硬前置 ✓。"""
        model = QZDAPChatModel(llm=_EchoLLM(), model_name="demo")
        reply = await model.ainvoke([HumanMessage(content="你好")])
        assert isinstance(reply.content, str)
        assert reply.content

    @pytest.mark.asyncio
    async def test_it_streams_incrementally(self) -> None:
        """**流式** ✓ —— 文本增量边到边推 ✓（§5.2.2 第 3 条 ✓）。"""
        model = QZDAPChatModel(llm=_EchoLLM(), model_name="demo")
        chunks = [chunk async for chunk in model.astream([HumanMessage(content="你好")])]
        assert len(chunks) >= 1
        assert all(isinstance(chunk.content, str) for chunk in chunks)

    def test_the_sync_path_says_no_loudly(self) -> None:
        """同步流式**明确报错** ✓（平台只有异步客户端 ✓）。

        ⚠️ 悄悄返回空会让调用方以为「模型没说话」✗✗。
        """
        model = QZDAPChatModel(llm=_EchoLLM())
        with pytest.raises(NotImplementedError):
            list(model.stream([HumanMessage(content="你好")]))


# ---------------------------------------------------------------------------
# TaskClassifier（A-03）
# ---------------------------------------------------------------------------


class TestTaskClassifier:
    def test_it_always_returns_a_classification(self) -> None:
        """**永远返回一个合法分类** ✓（不允许 None ✓）。"""
        classification = TaskClassifier().classify(
            message_count=0,
            tools_count=0,
            message_text="",
            agent_config=AgentRouteConfig(agent_id="a"),
        )
        assert isinstance(classification, TaskClassification)
        assert isinstance(classification.kind, TaskKind)
        assert 0.0 < classification.confidence <= 1.0

    def test_the_explicit_declaration_wins(self) -> None:
        classification = TaskClassifier().classify(
            message_count=1,
            tools_count=1,
            message_text="你好",
            agent_config=AgentRouteConfig(agent_id="a", deep_research=True),
        )
        assert classification.kind is TaskKind.DEEP_RESEARCH
        assert classification.confidence == 1.0
        assert classification.reason

    def test_the_fallback_is_the_weakest(self) -> None:
        """**默认 fallback 的置信度最低** ✓ —— 调用方据此决定要不要信 ✓。"""
        classification = TaskClassifier().classify(
            message_count=1,
            tools_count=1,
            message_text="你好",
            agent_config=AgentRouteConfig(agent_id="a"),
        )
        assert classification.kind is TaskKind.SIMPLE_QA
        assert classification.confidence < 1.0
