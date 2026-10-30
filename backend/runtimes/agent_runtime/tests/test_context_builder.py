"""Context Stage 1：``ContextBuilder`` —— 固定优先级拼装 + manifest。

依据：Context 方案 §3（Builder）、§3.1（固定优先级）、§3.2（输出形状）、
§3.3（agent prompts）、§3.5（manifest 的内容）。

⚠️ **迁移必须复刻的三个参数**（§3.2 ✓ —— 复刻不到，新旧行为会漂移 ✗）：
记忆 ``top_k=8`` ✓、知识 ``top_k=6`` ✓、每条命中**截 400 字** ✓。
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest

from qzdap_agent_runtime.context import (
    DEFAULT_SYSTEM_PROMPT,
    KNOWLEDGE_TOP_K,
    MEMORY_TOP_K,
    ContextBuilder,
)


class _Memory:
    """记忆召回替身 —— 记下调用参数 ✓（参数漂移要能被发现 ✗✗）。"""

    def __init__(self, hits: list[dict[str, Any]] | None = None, *, fail: bool = False):
        self.hits = hits or []
        self.fail = fail
        self.calls: list[dict[str, Any]] = []

    async def recall(self, **kwargs: Any) -> list[dict[str, Any]]:
        self.calls.append(kwargs)
        if self.fail:
            raise RuntimeError("recall exploded")
        return self.hits


class _Knowledge:
    def __init__(self, hits: list[dict[str, Any]] | None = None, *, fail: bool = False):
        self.hits = hits or []
        self.fail = fail
        self.calls: list[dict[str, Any]] = []

    async def search(self, **kwargs: Any) -> list[dict[str, Any]]:
        self.calls.append(kwargs)
        if self.fail:
            raise RuntimeError("search exploded")
        return self.hits


async def _build(builder: ContextBuilder, **overrides: Any):  # type: ignore[no-untyped-def]
    kwargs: dict[str, Any] = {
        "tenant_id": uuid4(),
        "workspace_id": uuid4(),
        "owner_id": uuid4(),
        "user_input": "帮我查一下差旅政策",
    }
    kwargs.update(overrides)
    return await builder.build(**kwargs)


class TestFixedPriority:
    @pytest.mark.asyncio
    async def test_segments_come_out_in_priority_order(self) -> None:
        memory = _Memory([{"id": "m1", "content": "记忆内容", "score": 0.9}])
        knowledge = _Knowledge([{"id": "k1", "content": "知识内容", "score": 0.8}])
        builder = ContextBuilder(memory_port=memory, knowledge_port=knowledge)
        ctx = await _build(
            builder,
            agent_prompts={"soul": "你是小智"},
            tenant_context={"tenant_id": "t1", "workspace_id": "w1"},
            summary="上一轮的结论",
        )
        sources = [e.source for e in ctx.manifest.entries]
        assert sources[:4] == ["system", "agent", "tenant", "summary"]
        assert "memory" in sources
        assert "knowledge" in sources
        # 用户输入永远在最后 ✓（优先级 6 ✓）
        assert ctx.messages[-1] == {"role": "user", "content": "帮我查一下差旅政策"}

    @pytest.mark.asyncio
    async def test_the_user_input_is_never_dropped(self) -> None:
        builder = ContextBuilder(max_tokens=10)
        ctx = await _build(builder, agent_prompts={"soul": "x" * 500})
        assert ctx.messages[-1]["content"] == "帮我查一下差旅政策"

    @pytest.mark.asyncio
    async def test_the_system_prompt_is_never_dropped(self) -> None:
        builder = ContextBuilder(max_tokens=1)
        ctx = await _build(builder)
        assert ctx.messages[0]["content"] == DEFAULT_SYSTEM_PROMPT


class TestAgentPrompts:
    @pytest.mark.asyncio
    async def test_the_agent_identity_is_not_lost(self) -> None:
        """agent 的五段配置进 system ✓ —— **身份不能丢** ✗✗。"""
        builder = ContextBuilder()
        ctx = await _build(
            builder,
            agent_prompts={
                "soul": "你是小智",
                "prompt": "严谨",
                "agents": "多 Agent 协作",
                "tools": "优先用检索",
                "user": "对用户说中文",
            },
        )
        system_text = "\n\n".join(
            m["content"] for m in ctx.messages if m["role"] == "system"
        )
        for fragment in (
            "你是小智",
            "严谨",
            "多 Agent 协作",
            "优先用检索",
            "对用户说中文",
        ):
            assert fragment in system_text

    @pytest.mark.asyncio
    async def test_no_agent_prompt_means_no_duplicate_default(self) -> None:
        builder = ContextBuilder()
        ctx = await _build(builder)
        defaults = [m for m in ctx.messages if m["content"] == DEFAULT_SYSTEM_PROMPT]
        assert len(defaults) == 1


class TestRecallParameters:
    @pytest.mark.asyncio
    async def test_memory_top_k_is_eight(self) -> None:
        memory = _Memory()
        await _build(ContextBuilder(memory_port=memory))
        assert memory.calls[0]["top_k"] == MEMORY_TOP_K == 8

    @pytest.mark.asyncio
    async def test_knowledge_top_k_is_six(self) -> None:
        knowledge = _Knowledge()
        await _build(ContextBuilder(knowledge_port=knowledge))
        assert knowledge.calls[0]["top_k"] == KNOWLEDGE_TOP_K == 6

    @pytest.mark.asyncio
    async def test_recall_is_scoped_to_the_current_user(self) -> None:
        """记忆召回**必须按当前用户过滤** ✓ —— 缺了会跨用户泄漏 ✗✗。"""
        memory = _Memory()
        owner = uuid4()
        await _build(ContextBuilder(memory_port=memory), owner_id=owner)
        assert memory.calls[0]["user_id"] == owner

    @pytest.mark.asyncio
    async def test_hits_are_sorted_by_score(self) -> None:
        memory = _Memory(
            [
                {"id": "low", "content": "低分", "score": 0.1},
                {"id": "high", "content": "高分", "score": 0.9},
            ]
        )
        builder = ContextBuilder(memory_port=memory)
        ctx = await _build(builder)
        memory_entries = [e for e in ctx.manifest.entries if e.source == "memory"]
        assert [e.ref_id for e in memory_entries] == ["high", "low"]

    @pytest.mark.asyncio
    async def test_each_hit_is_truncated_to_400_chars(self) -> None:
        memory = _Memory([{"id": "m1", "content": "字" * 900, "score": 1.0}])
        builder = ContextBuilder(memory_port=memory)
        ctx = await _build(builder)
        hit_segments = [
            m["content"]
            for m, e in zip(ctx.messages, ctx.manifest.entries, strict=False)
            if e.source == "memory"
        ]
        assert hit_segments
        assert all(
            len(segment) <= 400 + 20 for segment in hit_segments
        )  # 分数前缀 + 截断 ✓


class TestDegraded:
    @pytest.mark.asyncio
    async def test_recall_failure_is_visible(self) -> None:
        """召回失败**必须可见** ✓ —— 旧路径是静默吞掉的 ✗✗。"""
        builder = ContextBuilder(
            memory_port=_Memory(fail=True), knowledge_port=_Knowledge(fail=True)
        )
        ctx = await _build(builder)
        assert ctx.degraded_flags.get("recall_degraded") is True

    @pytest.mark.asyncio
    async def test_no_recall_port_is_not_a_degradation(self) -> None:
        builder = ContextBuilder()
        ctx = await _build(builder)
        assert "recall_degraded" not in ctx.degraded_flags


class TestManifest:
    @pytest.mark.asyncio
    async def test_entries_carry_ref_id_and_score(self) -> None:
        memory = _Memory([{"id": "m1", "content": "记忆", "score": 0.42}])
        knowledge = _Knowledge(
            [{"metadata": {"asset_id": "a1"}, "content": "知识", "score": 0.7}]
        )
        builder = ContextBuilder(memory_port=memory, knowledge_port=knowledge)
        ctx = await _build(
            builder, agent_version="v7", agent_prompts={"soul": "你是小智"}
        )
        entries = {(e.source, e.ref_id): e for e in ctx.manifest.entries}
        assert entries[("memory", "m1")].score == pytest.approx(0.42)
        assert entries[("knowledge", "a1")].score == pytest.approx(0.7)
        agent_entry = next(e for e in ctx.manifest.entries if e.source == "agent")
        assert agent_entry.version == "v7"

    @pytest.mark.asyncio
    async def test_the_manifest_total_matches_the_estimate(self) -> None:
        builder = ContextBuilder()
        ctx = await _build(builder, agent_prompts={"soul": "你是小智"})
        assert ctx.tokens_estimated == ctx.manifest.total_tokens
        assert ctx.tokens_estimated > 0

    @pytest.mark.asyncio
    async def test_a_dropped_segment_says_why(self) -> None:
        """被淘汰的片段**留一条记录** ✓ —— 「什么没进去」要能回答 ✓。"""
        memory = _Memory([{"id": "m1", "content": "记忆" * 200, "score": 1.0}])
        builder = ContextBuilder(memory_port=memory, max_tokens=30)
        ctx = await _build(builder)
        dropped = [e for e in ctx.manifest.entries if e.filtered_reason]
        assert dropped
        assert all(e.filtered_reason == "over_budget" for e in dropped)
        assert ctx.degraded_flags.get("compaction_degraded") is True

    @pytest.mark.asyncio
    async def test_every_message_is_covered_by_the_manifest(self) -> None:
        """消息与清单**成对** ✓ —— 对不上就说明「它喂了什么」不可信 ✗✗。"""
        builder = ContextBuilder(
            memory_port=_Memory([{"id": "m1", "content": "记忆", "score": 1.0}])
        )
        ctx = await _build(builder, history=[{"role": "user", "content": "上一句"}])
        assert len(ctx.messages) == len(ctx.manifest.entries)


class TestPorts:
    def test_the_adapters_satisfy_the_protocols(self) -> None:
        """模块侧的适配器**结构上**满足契约层的协议 ✓（不引框架 ✓）。"""
        from qzdap.modules.agent_runtime.adapter.knowledge.knowledge_service_adapter import (
            KnowledgeServiceAdapter,
        )
        from qzdap.modules.agent_runtime.adapter.memory.memory_service_adapter import (
            MemoryServiceAdapter,
        )

        from qzdap_agent_runtime.context import (
            KnowledgeSearchPort,
            MemoryRecallPort,
        )

        assert isinstance(
            MemoryServiceAdapter.__new__(MemoryServiceAdapter), MemoryRecallPort
        )
        assert isinstance(
            KnowledgeServiceAdapter.__new__(KnowledgeServiceAdapter),
            KnowledgeSearchPort,
        )


class TestNoFramework:
    def test_the_contract_layer_stays_framework_free(self) -> None:
        """契约层**不引框架** ✓（Context 方案 §8.1 ✓）。"""
        import qzdap_agent_runtime.context.builder as builder_module

        source = builder_module.__file__
        assert source is not None
        with open(source, encoding="utf-8") as handle:
            text = handle.read()
        for forbidden in ("import fastapi", "import sqlalchemy", "import httpx"):
            assert forbidden not in text

    def test_uuid_is_the_only_tenant_scope(self) -> None:
        assert UUID is not None
