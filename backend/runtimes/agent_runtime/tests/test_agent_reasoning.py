"""Agent Stage 1：模型侧 —— 取值链 ✓ / 失败转移链 ✓ / 工具调用装配 ✓。

依据：Agent 方案 §3.1（Reason / Plan ✓）、§5.2.1（取值链 ✓）、§5.2.2（调用
模型完成生成 ✓）、§8.1（``execution/llm_client.py`` ✓ / ``agent_loop/reason.py`` ✓）。

验收三条 ✓：**工具调用按分片装配完整再交出去** ✓ / **取值链的优先级不变** ✓
/ **文本增量边到边推** ✓。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessageChunk, HumanMessage

from qzdap_agent_runtime.agent_loop import Reasoner, ToolCallAccumulator
from qzdap_agent_runtime.execution import QZDAPChatModel
from qzdap_agent_runtime.execution.llm_client import LLMCaller
from qzdap_agent_runtime.ports import ActorContext
from qzdap_kernel.ids import ModelId
from qzdap_llm.client import ChatRequest, LLMChunk

TENANT = uuid4()
WORKSPACE = uuid4()


class _ScriptedLLM:
    """按脚本产出 chunk 的端口替身 ✓。"""

    def __init__(self, chunks: list[LLMChunk]) -> None:
        self._chunks = chunks
        self.calls: list[dict[str, Any]] = []

    async def stream(
        self,
        request: ChatRequest,
        *,
        model_id: ModelId | None = None,
        route_id: ModelId | None = None,
        fallback_model_ids: list[ModelId] | None = None,
        actor: ActorContext | None = None,
    ) -> AsyncIterator[LLMChunk]:
        self.calls.append(
            {
                "model": request.model,
                "model_id": model_id,
                "route_id": route_id,
                "fallback_model_ids": fallback_model_ids,
                "actor": actor,
            }
        )
        for chunk in self._chunks:
            yield chunk


class _Resolver:
    def __init__(self, model_id: ModelId | None) -> None:
        self._model_id = model_id
        self.calls: list[dict[str, Any]] = []

    async def resolve(
        self,
        *,
        tenant_id: Any,
        workspace_id: Any,
        upstream_model: str,
    ) -> ModelId | None:
        self.calls.append(
            {
                "tenant_id": tenant_id,
                "workspace_id": workspace_id,
                "upstream_model": upstream_model,
            }
        )
        return self._model_id


class TestTheValueChain:
    """§5.2.1 的取值链 ✓ —— **查表，不是决策** ✓。"""

    @pytest.mark.asyncio
    async def test_an_explicit_model_id_wins_over_the_resolver(self) -> None:
        model_id = ModelId(uuid4())
        resolver = _Resolver(ModelId(uuid4()))
        caller = LLMCaller(_ScriptedLLM([]), resolver=resolver)
        resolved = await caller.resolve(
            model_name="deepseek-chat",
            tenant_id=TENANT,
            workspace_id=WORKSPACE,
            model_id=model_id,
        )
        assert resolved.model_id == model_id
        assert resolver.calls == [], "给了 model_id 就不该再查表"

    @pytest.mark.asyncio
    async def test_the_route_wins_over_the_model_id(self) -> None:
        """**策略路由优先** ✓（§5.2.1 第 3 条 ✓）。"""
        route_id = ModelId(uuid4())
        model_id = ModelId(uuid4())
        caller = LLMCaller(_ScriptedLLM([]))
        resolved = await caller.resolve(
            model_name="deepseek-chat",
            tenant_id=TENANT,
            workspace_id=WORKSPACE,
            model_id=model_id,
            route_id=route_id,
        )
        assert resolved.route_id == route_id
        assert resolved.is_routed is True

    @pytest.mark.asyncio
    async def test_the_resolver_is_consulted_for_a_name(self) -> None:
        model_id = ModelId(uuid4())
        resolver = _Resolver(model_id)
        caller = LLMCaller(_ScriptedLLM([]), resolver=resolver)
        resolved = await caller.resolve(
            model_name="deepseek-chat",
            tenant_id=TENANT,
            workspace_id=WORKSPACE,
        )
        assert resolved.model_id == model_id
        assert resolver.calls[0]["tenant_id"] == TENANT
        assert resolver.calls[0]["upstream_model"] == "deepseek-chat"

    @pytest.mark.asyncio
    async def test_an_unresolved_model_falls_back_to_the_environment(self) -> None:
        """**查不到不是错误** ✓ —— 走环境默认模型 ✓（§5.2.1 细节 1 ✓）。"""
        caller = LLMCaller(_ScriptedLLM([]), resolver=_Resolver(None))
        resolved = await caller.resolve(
            model_name="不存在",
            tenant_id=TENANT,
            workspace_id=WORKSPACE,
        )
        assert resolved.model_id is None
        assert resolved.model_name == "不存在"

    @pytest.mark.asyncio
    async def test_the_fallback_chain_reaches_the_port(self) -> None:
        """**失败转移链交给端口** ✓（§5.2.1 第 5 条 ✓）。"""
        primary = ModelId(uuid4())
        fallback = ModelId(uuid4())
        llm = _ScriptedLLM([])
        caller = LLMCaller(llm)
        resolved = await caller.resolve(
            model_name="demo",
            tenant_id=TENANT,
            workspace_id=WORKSPACE,
            model_id=primary,
            fallback_model_ids=[fallback],
        )
        chunks = [
            chunk
            async for chunk in caller.stream(
                resolved=resolved, request=ChatRequest(model="demo", messages=[])
            )
        ]
        assert chunks == []
        assert llm.calls[0]["model_id"] == primary
        assert llm.calls[0]["fallback_model_ids"] == [fallback]


class TestToolCallAssembly:
    """§3.1 第 1 条 ✓ —— **分片必须装配完整再交出去** ✓。"""

    def test_indexed_fragments_are_merged(self) -> None:
        accumulator = ToolCallAccumulator()
        accumulator.add(
            [
                {"id": "call-1", "index": 0, "name": "sea", "args": ""},
                {"id": "call-1", "index": 0, "name": "rch", "args": '{"q":'},
            ]
        )
        accumulator.add(
            [
                {"id": "call-1", "index": 0, "name": "", "args": '"x"}'},
            ]
        )
        calls = accumulator.finish()
        assert len(calls) == 1
        assert calls[0]["name"] == "search"
        assert calls[0]["args"] == {"q": "x"}
        assert calls[0]["id"] == "call-1"

    def test_two_calls_stay_separate(self) -> None:
        accumulator = ToolCallAccumulator()
        accumulator.add(
            [
                {"id": "a", "index": 0, "name": "first", "args": "{}"},
                {"id": "b", "index": 1, "name": "second", "args": "{}"},
            ]
        )
        calls = accumulator.finish()
        assert [call["name"] for call in calls] == ["first", "second"]

    def test_mixed_argument_representations_are_rejected(self) -> None:
        """**字符串参数与 dict 参数不容混用** ✓ —— 半截参数比报错更糟 ✗✗。"""
        accumulator = ToolCallAccumulator()
        accumulator.add([{"id": "a", "index": 0, "name": "x", "args": '{"q":'}])
        with pytest.raises(TypeError):
            accumulator.add([{"id": "a", "index": 0, "name": "", "args": {"q": "x"}}])

    def test_the_thought_signature_is_kept(self) -> None:
        accumulator = ToolCallAccumulator()
        accumulator.add(
            [
                {
                    "id": "a",
                    "index": 0,
                    "name": "x",
                    "args": "{}",
                    "thought_signature": "sig",
                }
            ]
        )
        assert accumulator.finish()[0]["thought_signature"] == "sig"


class TestReasoner:
    @pytest.mark.asyncio
    async def test_the_text_deltas_are_streamed(self) -> None:
        """**文本边到边推** ✓（§3.1 第 2 条 ✓）。"""
        llm = _ScriptedLLM(
            [
                LLMChunk(model="demo", delta="我"),
                LLMChunk(model="demo", delta="在"),
            ]
        )
        reasoner = Reasoner(QZDAPChatModel(llm=llm, model_name="demo"))
        chunks = [chunk async for chunk in reasoner.reason(messages=[HumanMessage(content="你好")])]
        assert [chunk.content for chunk in chunks] == ["我", "在"]

    @pytest.mark.asyncio
    async def test_the_tool_calls_are_assembled_before_handover(self) -> None:
        """**装配完整才交出去** ✓ —— 调用方不会拿到半截参数 ✗✗。"""
        llm = _ScriptedLLM(
            [
                LLMChunk(
                    model="demo",
                    delta="",
                    tool_calls=[{"id": "call-1", "index": 0, "name": "sea", "arguments": ""}],
                ),
                LLMChunk(
                    model="demo",
                    delta="",
                    tool_calls=[
                        {
                            "id": "call-1",
                            "index": 0,
                            "name": "rch",
                            "arguments": '{"q":"x"}',
                        }
                    ],
                ),
            ]
        )
        reasoner = Reasoner(QZDAPChatModel(llm=llm, model_name="demo"))
        chunks = [
            chunk async for chunk in reasoner.reason(messages=[HumanMessage(content="搜一下")])
        ]
        assembled = [call for chunk in chunks for call in chunk.tool_calls]
        assert len(assembled) == 1
        assert assembled[0]["name"] == "search"
        assert assembled[0]["args"] == {"q": "x"}

    @pytest.mark.asyncio
    async def test_the_usage_is_carried_on_the_chunk(self) -> None:
        """**用量走 usage_metadata** ✓（§3.1 第 4 条 ✓）。"""
        from qzdap_llm.client import Usage

        llm = _ScriptedLLM(
            [
                LLMChunk(
                    model="demo",
                    delta="好",
                    usage=Usage(input_tokens=7, output_tokens=3),
                )
            ]
        )
        reasoner = Reasoner(QZDAPChatModel(llm=llm, model_name="demo"))
        chunks = [chunk async for chunk in reasoner.reason(messages=[HumanMessage(content="你好")])]
        assert chunks[0].usage_metadata == {
            "input_tokens": 7,
            "output_tokens": 3,
            "total_tokens": 10,
        }


class TestChatModelToolTranslation:
    @pytest.mark.asyncio
    async def test_the_tool_call_deltas_are_translated(self) -> None:
        """**平台的工具调用 delta → LangChain 的 tool_call_chunks** ✓。"""
        llm = _ScriptedLLM(
            [
                LLMChunk(
                    model="demo",
                    delta="",
                    tool_calls=[{"id": "call-1", "index": 0, "name": "sea", "arguments": "{"}],
                )
            ]
        )
        model = QZDAPChatModel(llm=llm, model_name="demo")
        chunks = [chunk async for chunk in model.astream([HumanMessage(content="搜一下")])]
        raw = chunks[0].tool_call_chunks
        assert raw and raw[0]["name"] == "sea"
        assert raw[0]["args"] == "{"
        assert raw[0]["id"] == "call-1"
        assert isinstance(chunks[0], AIMessageChunk)
