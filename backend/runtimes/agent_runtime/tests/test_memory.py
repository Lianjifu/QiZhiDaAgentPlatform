"""Tests for memory layer (§13.4 LayeredMemory)."""

from __future__ import annotations

import pytest

from qzdap_agent_runtime.memory import (
    InMemoryLayeredMemory,
    L1Source,
    L2Fact,
    L3Chunk,
)
from qzdap_agent_runtime.ports import LayeredMemory


# ---------------------------------------------------------------------------
# InMemoryLayeredMemory L1 / L2 / L3 基本召回
# ---------------------------------------------------------------------------


def test_in_memory_layered_memory_satisfies_protocol() -> None:
    """InMemoryLayeredMemory 必须实现 LayeredMemory Protocol。"""
    assert isinstance(InMemoryLayeredMemory(), LayeredMemory)


class TestRecallMemoryL1:
    def test_recall_from_messages(self) -> None:
        mem = InMemoryLayeredMemory()
        mem.set_l1(L1Source(
            session_id="s-1",
            messages=(
                {"role": "user", "content": "Python 是动态类型语言"},
                {"role": "assistant", "content": "是的"},
            ),
            rolling_summary="",
        ))
        hits = mem.recall_memory(
            query="动态类型",
            tenant_id="t-1",
            workspace_id="w-1",
            user_id="u-1",
            session_id="s-1",
            policy={"top_k": 5, "threshold": 0.05},
        )
        assert len(hits) == 1
        assert hits[0].layer == "l1"
        assert "Python" in hits[0].content
        assert hits[0].source_id == "s-1:msg:0"

    def test_recall_from_rolling_summary(self) -> None:
        mem = InMemoryLayeredMemory()
        mem.set_l1(L1Source(
            session_id="s-1",
            messages=(),
            rolling_summary="用户偏好使用中文回答",
        ))
        hits = mem.recall_memory(
            query="中文",
            tenant_id="t-1",
            workspace_id="w-1",
            user_id="u-1",
            session_id="s-1",
            policy={"top_k": 5, "threshold": 0.05},
        )
        assert len(hits) == 1
        assert hits[0].source_id == "s-1:summary"

    def test_recall_threshold_filters_low_score(self) -> None:
        mem = InMemoryLayeredMemory()
        mem.set_l1(L1Source(
            session_id="s-1",
            messages=({"role": "user", "content": "天气晴朗"},),
            rolling_summary="",
        ))
        # 高阈值过滤不相关 query
        hits = mem.recall_memory(
            query="完全不相关的内容",
            tenant_id="t-1",
            workspace_id="w-1",
            user_id="u-1",
            session_id="s-1",
            policy={"top_k": 5, "threshold": 0.9},
        )
        assert hits == []

    def test_recall_top_k_limit(self) -> None:
        mem = InMemoryLayeredMemory()
        mem.set_l1(L1Source(
            session_id="s-1",
            messages=tuple(
                {"role": "user", "content": f"动态类型 {i}"} for i in range(10)
            ),
            rolling_summary="",
        ))
        hits = mem.recall_memory(
            query="动态类型",
            tenant_id="t-1",
            workspace_id="w-1",
            user_id="u-1",
            session_id="s-1",
            policy={"top_k": 3, "threshold": 0.01},
        )
        assert len(hits) == 3


class TestRecallMemoryL2:
    def test_recall_fact_by_user(self) -> None:
        mem = InMemoryLayeredMemory()
        mem.add_l2_fact(L2Fact(
            fact_id="f-1",
            tenant_id="t-1",
            workspace_id="w-1",
            user_id="u-1",
            content="用户偏好使用 Rust 编程",
            confidence=0.95,
        ))
        hits = mem.recall_memory(
            query="Rust 编程",
            tenant_id="t-1",
            workspace_id="w-1",
            user_id="u-1",
            session_id="s-1",
            policy={"top_k": 5, "threshold": 0.05},
        )
        assert len(hits) == 1
        assert hits[0].layer == "l2"
        assert hits[0].metadata["confidence"] == 0.95

    def test_recall_filters_other_tenant(self) -> None:
        """§13.4 tenant_id filter：跨租户事实不可召回。"""
        mem = InMemoryLayeredMemory()
        mem.add_l2_fact(L2Fact(
            fact_id="f-1",
            tenant_id="t-other",
            workspace_id="w-1",
            user_id="u-1",
            content="Python 编码规范",
            confidence=1.0,
        ))
        hits = mem.recall_memory(
            query="Python",
            tenant_id="t-1",  # 不同 tenant
            workspace_id="w-1",
            user_id="u-1",
            session_id="s-1",
            policy={"top_k": 5, "threshold": 0.05},
        )
        assert hits == []

    def test_recall_filters_other_user(self) -> None:
        """§13.4 user scope：其他用户的事实不可召回（除非 user_id='*'）。"""
        mem = InMemoryLayeredMemory()
        mem.add_l2_fact(L2Fact(
            fact_id="f-1",
            tenant_id="t-1",
            workspace_id="w-1",
            user_id="u-other",
            content="Python 编码规范",
            confidence=1.0,
        ))
        hits = mem.recall_memory(
            query="Python",
            tenant_id="t-1",
            workspace_id="w-1",
            user_id="u-1",
            session_id="s-1",
            policy={"top_k": 5, "threshold": 0.05},
        )
        assert hits == []

    def test_wildcard_user_id_matches_any(self) -> None:
        """user_id='*' 必须被任何 user 召回。"""
        mem = InMemoryLayeredMemory()
        mem.add_l2_fact(L2Fact(
            fact_id="f-1",
            tenant_id="t-1",
            workspace_id="w-1",
            user_id="*",
            content="公司通用条款",
            confidence=1.0,
        ))
        hits = mem.recall_memory(
            query="通用",
            tenant_id="t-1",
            workspace_id="w-1",
            user_id="u-anyone",
            session_id="s-1",
            policy={"top_k": 5, "threshold": 0.05},
        )
        assert len(hits) == 1


class TestRecallKnowledgeL3:
    def test_recall_chunk_with_acl(self) -> None:
        mem = InMemoryLayeredMemory()
        mem.add_l3_chunk(L3Chunk(
            chunk_id="c-1",
            asset_id="asset-1",
            workspace_id="w-1",
            content="RAG 检索增强生成介绍",
            version="v1",
            acl_allow=("w-1",),
        ))
        hits = mem.recall_knowledge(
            query="RAG 检索",
            tenant_id="t-1",
            workspace_id="w-1",
        )
        assert len(hits) == 1
        assert hits[0].layer == "l3"
        assert hits[0].metadata["asset_id"] == "asset-1"
        assert "asset://asset-1" in (hits[0].citation or "")

    def test_recall_filters_other_workspace(self) -> None:
        """§13.4 ACL：跨 workspace 不可召回。"""
        mem = InMemoryLayeredMemory()
        mem.add_l3_chunk(L3Chunk(
            chunk_id="c-1",
            asset_id="asset-1",
            workspace_id="w-other",
            content="机密文档",
            version="v1",
            acl_allow=("w-other",),
        ))
        hits = mem.recall_knowledge(
            query="机密",
            tenant_id="t-1",
            workspace_id="w-1",  # 不可访问 w-other
        )
        assert hits == []

    def test_recall_respects_package_ids_filter(self) -> None:
        mem = InMemoryLayeredMemory()
        mem.add_l3_chunk(L3Chunk(
            chunk_id="c-1", asset_id="asset-1", workspace_id="w-1",
            content="RAG 介绍", version="v1",
        ))
        mem.add_l3_chunk(L3Chunk(
            chunk_id="c-2", asset_id="asset-2", workspace_id="w-1",
            content="RAG 高级", version="v1",
        ))
        hits = mem.recall_knowledge(
            query="RAG",
            tenant_id="t-1",
            workspace_id="w-1",
            package_ids=("asset-1",),  # 只允许 asset-1
        )
        assert len(hits) == 1
        assert hits[0].metadata["asset_id"] == "asset-1"


# ---------------------------------------------------------------------------
# write_l2 幂等性 (§5.4 同 content_hash 必须幂等)
# ---------------------------------------------------------------------------


class TestWriteL2Idempotency:
    def test_same_content_hash_dedup(self) -> None:
        mem = InMemoryLayeredMemory()
        mem.write_l2({
            "fact_id": "f-1",
            "tenant_id": "t-1",
            "workspace_id": "w-1",
            "user_id": "u-1",
            "content": "用户偏好 Python",
            "confidence": 0.9,
            "content_hash": "hash-abc",
        })
        mem.write_l2({
            "fact_id": "f-2",  # 不同 ID 但同 hash
            "tenant_id": "t-1",
            "workspace_id": "w-1",
            "user_id": "u-1",
            "content": "用户偏好 Python",
            "confidence": 0.95,
            "content_hash": "hash-abc",
        })
        # 只能召回 1 条
        hits = mem.recall_memory(
            query="Python 偏好",
            tenant_id="t-1",
            workspace_id="w-1",
            user_id="u-1",
            session_id="s-1",
            policy={"top_k": 5, "threshold": 0.05},
        )
        assert len(hits) == 1

    def test_different_content_hash_keeps_both(self) -> None:
        mem = InMemoryLayeredMemory()
        mem.write_l2({
            "fact_id": "f-1",
            "tenant_id": "t-1",
            "workspace_id": "w-1",
            "user_id": "u-1",
            "content": "Python 偏好",
            "content_hash": "hash-1",
        })
        mem.write_l2({
            "fact_id": "f-2",
            "tenant_id": "t-1",
            "workspace_id": "w-1",
            "user_id": "u-1",
            "content": "Rust 偏好",
            "content_hash": "hash-2",
        })
        hits = mem.recall_memory(
            query="编程偏好",
            tenant_id="t-1",
            workspace_id="w-1",
            user_id="u-1",
            session_id="s-1",
            policy={"top_k": 5, "threshold": 0.05},
        )
        assert len(hits) == 2


# ---------------------------------------------------------------------------
# 异常输入 (Stage 3 验证要求 §16: 知识不可用时主回答可继续)
# ---------------------------------------------------------------------------


class TestGracefulDegradation:
    def test_recall_empty_query_returns_empty(self) -> None:
        mem = InMemoryLayeredMemory()
        mem.set_l1(L1Source(
            session_id="s-1",
            messages=({"role": "user", "content": "some content"},),
            rolling_summary="",
        ))
        # 空 query 不应抛异常
        hits = mem.recall_memory(
            query="",
            tenant_id="t-1",
            workspace_id="w-1",
            user_id="u-1",
            session_id="s-1",
            policy={},
        )
        assert hits == []

    def test_recall_with_no_l1_source(self) -> None:
        """无 L1 源（L1 cache miss）必须返回空，不抛异常。"""
        mem = InMemoryLayeredMemory()
        hits = mem.recall_memory(
            query="anything",
            tenant_id="t-1",
            workspace_id="w-1",
            user_id="u-1",
            session_id="s-missing",  # 没 set_l1
            policy={},
        )
        assert hits == []

    def test_recall_knowledge_with_no_chunks(self) -> None:
        mem = InMemoryLayeredMemory()
        hits = mem.recall_knowledge(
            query="anything",
            tenant_id="t-1",
            workspace_id="w-1",
        )
        assert hits == []