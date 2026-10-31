"""Memory Stage 2：检索的**七步流水线** ✓。

依据：Memory 方案 §3.1（七步 ✓）、§3.4（阈值与 abstain ✓）、
§4.4（去重 ✓）、§3.5（provenance ✓）、C10（读取侧降级 ✓）。
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from qzdap_agent_runtime.memory.retrieval import (
    Candidate,
    RetrievalPipeline,
)


class _Port:
    """候选端口替身 ✓ —— 记下调用参数 ✓（过滤有没有下推要看这里 ✓）。"""

    def __init__(self, candidates: list[Candidate] | None = None, *, fail: bool = False):
        self.candidates = candidates or []
        self.fail = fail
        self.calls: list[dict] = []

    async def search(self, **kwargs) -> list[Candidate]:  # type: ignore[no-untyped-def]
        self.calls.append(kwargs)
        if self.fail:
            raise RuntimeError("vector store is down")
        return list(self.candidates)


def _candidate(ref_id: str, score: float, **kwargs) -> Candidate:  # type: ignore[no-untyped-def]
    return Candidate(
        ref_id=ref_id,
        layer=kwargs.pop("layer", "l2"),
        content=kwargs.pop("content", f"内容 {ref_id}"),
        score=score,
        **kwargs,
    )


class TestVectorFirst:
    @pytest.mark.asyncio
    async def test_the_vector_candidates_come_first(self) -> None:
        vector = _Port([_candidate("v1", 0.9)])
        lexical = _Port([_candidate("l1", 0.5)])
        pipeline = RetrievalPipeline(lexical=lexical, vector=vector)
        outcome = await pipeline.recall(
            tenant_id=uuid4(),
            workspace_id=uuid4(),
            user_id=None,
            query="报销",
        )
        assert [hit["ref_id"] for hit in outcome.hits] == ["v1", "l1"]

    @pytest.mark.asyncio
    async def test_the_scores_are_fused(self) -> None:
        """融合：0.7 * 向量 + 0.3 * 词法 ✓（与旧路径同口径 ✓）。"""
        vector = _Port([_candidate("v1", 1.0)])
        lexical = _Port([_candidate("v1", 1.0)])
        pipeline = RetrievalPipeline(lexical=lexical, vector=vector)
        outcome = await pipeline.recall(
            tenant_id=uuid4(),
            workspace_id=uuid4(),
            user_id=None,
            query="报销",
        )
        assert outcome.hits[0]["score"] == pytest.approx(1.0)

    @pytest.mark.asyncio
    async def test_the_scope_is_pushed_to_the_ports(self) -> None:
        """**作用域过滤下推到候选端口** ✓（不在 Python 侧逐行过滤 ✗）。"""
        vector = _Port([])
        lexical = _Port([])
        pipeline = RetrievalPipeline(lexical=lexical, vector=vector)
        tenant, workspace, user = uuid4(), uuid4(), uuid4()
        await pipeline.recall(
            tenant_id=tenant,
            workspace_id=workspace,
            user_id=user,
            query="报销",
        )
        assert lexical.calls[0]["user_id"] == user
        assert lexical.calls[0]["workspace_id"] == workspace
        assert vector.calls[0]["user_id"] == user

    @pytest.mark.asyncio
    async def test_the_candidate_set_is_top_k_times_four(self) -> None:
        """候选集 = ``top_k × 4`` ✓（与 Context 的降级序一致 ✓）。"""
        lexical = _Port([])
        pipeline = RetrievalPipeline(lexical=lexical, vector=None)
        await pipeline.recall(
            tenant_id=uuid4(),
            workspace_id=uuid4(),
            user_id=None,
            query="报销",
            top_k=5,
        )
        assert lexical.calls[0]["limit"] == 20


class TestThresholdAndAbstain:
    @pytest.mark.asyncio
    async def test_low_scores_are_dropped(self) -> None:
        lexical = _Port([_candidate("l1", 0.01)])
        pipeline = RetrievalPipeline(lexical=lexical, vector=None, threshold=0.15)
        outcome = await pipeline.recall(
            tenant_id=uuid4(),
            workspace_id=uuid4(),
            user_id=None,
            query="报销",
        )
        assert outcome.hits == []

    @pytest.mark.asyncio
    async def test_an_empty_result_is_an_abstention(self) -> None:
        """「没找到够格的」要能与「没有相关知识」**区分** ✓。"""
        lexical = _Port([_candidate("l1", 0.01)])
        pipeline = RetrievalPipeline(lexical=lexical, vector=None, threshold=0.15)
        outcome = await pipeline.recall(
            tenant_id=uuid4(),
            workspace_id=uuid4(),
            user_id=None,
            query="报销",
        )
        assert outcome.abstained is True

    @pytest.mark.asyncio
    async def test_an_empty_query_abstains(self) -> None:
        pipeline = RetrievalPipeline(lexical=_Port([]), vector=None)
        outcome = await pipeline.recall(
            tenant_id=uuid4(),
            workspace_id=uuid4(),
            user_id=None,
            query="   ",
        )
        assert outcome.abstained is True


class TestDeduplication:
    @pytest.mark.asyncio
    async def test_the_same_ref_is_kept_once(self) -> None:
        vector = _Port([_candidate("v1", 0.9), _candidate("v1", 0.8)])
        pipeline = RetrievalPipeline(lexical=_Port([]), vector=vector)
        outcome = await pipeline.recall(
            tenant_id=uuid4(),
            workspace_id=uuid4(),
            user_id=None,
            query="报销",
        )
        assert len(outcome.hits) == 1

    @pytest.mark.asyncio
    async def test_the_same_content_hash_is_kept_once(self) -> None:
        """**内容哈希相同**也算重复 ✓（去重的第二道 ✓ —— §4.4 ✓）。"""
        vector = _Port(
            [
                _candidate("v1", 0.9, content_hash="h1"),
                _candidate("v2", 0.8, content_hash="h1"),
            ]
        )
        pipeline = RetrievalPipeline(lexical=_Port([]), vector=vector)
        outcome = await pipeline.recall(
            tenant_id=uuid4(),
            workspace_id=uuid4(),
            user_id=None,
            query="报销",
        )
        assert len(outcome.hits) == 1


class TestProvenance:
    @pytest.mark.asyncio
    async def test_each_hit_carries_its_provenance(self) -> None:
        vector = _Port(
            [
                _candidate(
                    "v1",
                    0.9,
                    scope="user",
                    used_count=3,
                    version="2",
                    created_at="2026-10-30T00:00:00+00:00",
                )
            ]
        )
        pipeline = RetrievalPipeline(lexical=_Port([]), vector=vector)
        outcome = await pipeline.recall(
            tenant_id=uuid4(),
            workspace_id=uuid4(),
            user_id=None,
            query="报销",
        )
        hit = outcome.hits[0]
        assert hit["scope"] == "user"
        assert hit["used_count"] == 3
        assert hit["version"] == "2"
        assert hit["created_at"].startswith("2026-10-30")


class TestDegradation:
    @pytest.mark.asyncio
    async def test_a_broken_vector_store_falls_back_to_lexical(self) -> None:
        """向量库不可用 → **纯词法** ✓（C10 ✓）—— 且**降级可见** ✓。"""
        vector = _Port([], fail=True)
        lexical = _Port([_candidate("l1", 0.9)])
        pipeline = RetrievalPipeline(lexical=lexical, vector=vector)
        outcome = await pipeline.recall(
            tenant_id=uuid4(),
            workspace_id=uuid4(),
            user_id=None,
            query="报销",
        )
        assert [hit["ref_id"] for hit in outcome.hits] == ["l1"]
        assert outcome.degraded is True
        assert outcome.degraded_reason == "vector_unavailable"

    @pytest.mark.asyncio
    async def test_no_vector_port_is_not_a_degradation(self) -> None:
        """没配向量**不是故障** ✓（只是没有向量这一路 ✓）。"""
        pipeline = RetrievalPipeline(lexical=_Port([_candidate("l1", 0.9)]), vector=None)
        outcome = await pipeline.recall(
            tenant_id=uuid4(),
            workspace_id=uuid4(),
            user_id=None,
            query="报销",
        )
        assert outcome.degraded is False
