"""Tests for context layer + Stage 3 node implementations."""

from __future__ import annotations

import pytest

from qzdap_agent_runtime.context import (
    Compactor,
    ContextAssembler,
    InMemorySummaryModel,
    SummaryError,
    estimate_tokens,
)
from qzdap_agent_runtime.graph import nodes
from qzdap_agent_runtime.memory import (
    InMemoryLayeredMemory,
    L1Source,
    L2Fact,
    L3Chunk,
)


@pytest.fixture(autouse=True)
def _reset_deps():
    yield
    nodes.reset_default_dependencies()


# ---------------------------------------------------------------------------
# estimate_tokens
# ---------------------------------------------------------------------------


class TestEstimateTokens:
    def test_cjk_counts_as_one_per_char(self) -> None:
        assert estimate_tokens("中文测试") == 4

    def test_ascii_uses_four_chars_per_token(self) -> None:
        # "abcdefgh" = 8 chars → 2 tokens
        assert estimate_tokens("abcdefgh") == 2

    def test_empty_string_is_zero(self) -> None:
        assert estimate_tokens("") == 0

    def test_mixed_content(self) -> None:
        # "Hello中文" = 5 ASCII + 2 CJK = 2 + 2 = 4 tokens
        assert estimate_tokens("Hello中文") == 4


# ---------------------------------------------------------------------------
# ContextAssembler
# ---------------------------------------------------------------------------


class TestContextAssembler:
    def test_assemble_writes_manifest_entries(self) -> None:
        a = ContextAssembler(max_tokens=100_000)
        ctx = a.assemble(
            system_prompt="system prompt",
            agent_config={"agent_id": "agt-1", "version": "v1"},
            tenant_context={"tenant_id": "t-1", "workspace_id": "w-1", "user_id": "u-1"},
            rolling_summary="summary text",
            memory_hits=[{"layer": "l1", "content": "mem content"}],
            knowledge_hits=[{"metadata": {"asset_id": "k-1"}, "content": "know content"}],
            recent_messages=[{"role": "user", "content": "user msg"}],
        )
        sources = [e.source for e in ctx.manifest.entries]
        # §5.3 固定优先级
        assert sources == [
            "system", "agent", "tenant",
            "summary", "memory", "knowledge", "recent",
        ]
        # manifest total 包含所有
        assert ctx.manifest.total_tokens > 0

    def test_assemble_no_memory_no_knowledge(self) -> None:
        a = ContextAssembler()
        ctx = a.assemble(
            system_prompt="sys",
            agent_config={"agent_id": "a", "version": "v1"},
            tenant_context={"tenant_id": "t", "workspace_id": "w", "user_id": "u"},
            rolling_summary="",
            memory_hits=[],
            knowledge_hits=[],
            recent_messages=[],
        )
        sources = [e.source for e in ctx.manifest.entries]
        # 空 summary / memory / knowledge 不应产生 manifest entry
        assert "summary" not in sources
        assert "memory" not in sources
        assert "knowledge" not in sources

    def test_assemble_budget_exceeded_marks_degraded(self) -> None:
        a = ContextAssembler(max_tokens=10)  # 极小 budget
        ctx = a.assemble(
            system_prompt="很长的系统提示，包含大量内容",
            agent_config={"agent_id": "a", "version": "v1"},
            tenant_context={"tenant_id": "t", "workspace_id": "w", "user_id": "u"},
            rolling_summary="",
            memory_hits=[],
            knowledge_hits=[],
            recent_messages=[],
        )
        # §5.3 超 budget 必须标记 degraded
        assert ctx.degraded_flags.get("compaction_degraded") is True


# ---------------------------------------------------------------------------
# Compactor
# ---------------------------------------------------------------------------


class _FailSummary:
    """模拟摘要模型失败。"""

    async def summarize(self, text: str) -> str:
        raise SummaryError("rate limited")


class TestCompactor:
    async def test_no_compaction_when_under_budget(self) -> None:
        c = Compactor(InMemorySummaryModel())
        msgs = [{"role": "user", "content": "short"}]
        r = c.compact(msgs, existing_summary="", target_tokens=1000)
        assert r.degraded is False
        assert r.removed_message_ids == []
        assert r.tokens_after == r.tokens_before

    async def test_compaction_with_summary_succeeds(self) -> None:
        c = Compactor(InMemorySummaryModel(max_chars=50))
        msgs = [
            {"role": "user", "content": "msg " + "x" * 100, "message_id": f"m-{i}"}
            for i in range(10)
        ]
        r = c.compact(msgs, existing_summary="", target_tokens=20)
        assert r.degraded is False
        assert r.tokens_after < r.tokens_before
        # 摘要必须存在
        assert r.rolling_summary
        # 必须有 removed ids
        assert len(r.removed_message_ids) > 0

    async def test_compaction_falls_back_on_summary_failure(self) -> None:
        """§5.3 摘要失败时降级为确定性窗口压缩 + compaction_degraded=true。"""
        c = Compactor(_FailSummary())  # type: ignore[arg-type]
        msgs = [
            {"role": "user", "content": "x" * 50, "message_id": f"m-{i}"}
            for i in range(20)
        ]
        r = c.compact(msgs, existing_summary="", target_tokens=10)
        assert r.degraded is True
        # 摘要必须是 deterministic compaction 标记
        assert "deterministic" in r.rolling_summary
        # 至少 15 条被移除 (20 - 5 = 15)
        assert len(r.removed_message_ids) >= 15


# ---------------------------------------------------------------------------
# Stage 3 节点: recall_memory_and_knowledge
# ---------------------------------------------------------------------------


class TestRecallMemoryAndKnowledgeNode:
    async def test_passthrough_when_no_memory_injected(self) -> None:
        out = nodes.recall_memory_and_knowledge({})  # type: ignore[arg-type]
        assert out == {
            "memory_hits": [],
            "knowledge_hits": [],
        }

    async def test_recall_returns_hits_from_memory(self) -> None:
        mem = InMemoryLayeredMemory()
        mem.set_l1(L1Source(
            session_id="s-1",
            messages=({"role": "user", "content": "Python 动态类型"},),
            rolling_summary="",
        ))
        nodes.set_default_memory(mem)
        out = nodes.recall_memory_and_knowledge({
            "session_id": "s-1",
            "tenant_id": "t-1",
            "workspace_id": "w-1",
            "messages": [{"role": "user", "content": "Python 动态类型"}],
        })
        # 必须有 hit
        assert len(out["memory_hits"]) >= 1
        # degraded.recall_degraded 必须是 false
        assert out["degraded"]["recall_degraded"] is False

    async def test_recall_failure_marks_degraded(self) -> None:
        class _FailMemory:
            async def recall_memory(self, **kwargs):  # type: ignore[no-untyped-def]
                raise RuntimeError("vector db down")

            async def recall_knowledge(self, **kwargs):  # type: ignore[no-untyped-def]
                raise RuntimeError("vector db down")

        nodes.set_default_memory(_FailMemory())  # type: ignore[arg-type]
        out = nodes.recall_memory_and_knowledge({
            "session_id": "s-1",
            "tenant_id": "t-1",
            "workspace_id": "w-1",
            "messages": [{"role": "user", "content": "test"}],
        })
        # 主路径不抛异常
        assert out["memory_hits"] == []
        assert out["knowledge_hits"] == []
        # degraded.recall_degraded 必须为 true
        assert out["degraded"]["recall_degraded"] is True


# ---------------------------------------------------------------------------
# Stage 3 节点: assemble_context
# ---------------------------------------------------------------------------


class TestAssembleContextNode:
    async def test_passthrough_when_no_assembler(self) -> None:
        out = nodes.assemble_context({})  # type: ignore[arg-type]
        assert out == {}

    async def test_assemble_writes_context_manifest(self) -> None:
        a = ContextAssembler(max_tokens=100_000)
        nodes.set_default_assembler(a)
        out = nodes.assemble_context({
            "agent_id": "agt-1",
            "agent_version": "v1",
            "tenant_id": "t-1",
            "workspace_id": "w-1",
            "memory_hits": [{"layer": "l1", "content": "x"}],
            "knowledge_hits": [{"metadata": {"asset_id": "k-1"}, "content": "y"}],
        })
        assert "context_manifest" in out
        # 至少包含 system / agent / tenant / memory / knowledge 5 个 entry
        entries = out["context_manifest"]["entries"]
        assert len(entries) >= 5


# ---------------------------------------------------------------------------
# Stage 3 节点: compact_if_needed
# ---------------------------------------------------------------------------


class TestCompactIfNeededNode:
    async def test_passthrough_when_no_compactor(self) -> None:
        # 不注入 compactor → 默认 Compactor 已存在, 但 messages 空时返回 {}
        out = nodes.compact_if_needed({"messages": []})
        assert out == {}

    def test_compact_with_messages(self) -> None:
        c = Compactor(InMemorySummaryModel(max_chars=30))
        nodes.set_default_compactor(c)
        # 50 msgs × 500 chars = 6250 tokens > 4000 target → 必须 compact
        msgs = [
            {"role": "user", "content": "x" * 500, "message_id": f"m-{i}"}
            for i in range(50)
        ]
        out = nodes.compact_if_needed({
            "messages": msgs,
            "rolling_summary": "",
        })
        # 摘要必须写入
        assert out["rolling_summary"]
        # manifest 包含 compaction 信息
        assert "compaction" in out["context_manifest"]