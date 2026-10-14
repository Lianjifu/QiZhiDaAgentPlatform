"""Tests for Stage 7b: OnlineEvaluator + EngineSwitch (灰度)."""

from __future__ import annotations

import pytest

from qzdap_agent_runtime.evaluation import (
    EngineSwitch,
    EvalMetric,
    EvalRecord,
    InMemoryOnlineEvaluator,
    OnlineEvaluator,
    RolloutPolicy,
)
from qzdap_agent_runtime.graph import nodes
from qzdap_agent_runtime.observability import UsageRecord, UsageTracker


@pytest.fixture(autouse=True)
def _reset_deps():
    yield
    nodes.reset_default_dependencies()


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


def test_in_memory_evaluator_satisfies_protocol() -> None:
    assert isinstance(InMemoryOnlineEvaluator(), OnlineEvaluator)


# ---------------------------------------------------------------------------
# EvalMetric / EvalRecord
# ---------------------------------------------------------------------------


class TestEvalMetric:
    def test_default_zero_metrics(self) -> None:
        m = EvalMetric()
        for v in m.to_dict().values():
            assert v == 0.0

    def test_to_dict_returns_all_5(self) -> None:
        m = EvalMetric(recall_at_k=0.8, mrr=0.5, ndcg=0.7, groundedness=0.9, citation_coverage=0.6)
        d = m.to_dict()
        assert d == {
            "recall_at_k": 0.8,
            "mrr": 0.5,
            "ndcg": 0.7,
            "groundedness": 0.9,
            "citation_coverage": 0.6,
        }


# ---------------------------------------------------------------------------
# InMemoryOnlineEvaluator
# ---------------------------------------------------------------------------


class TestInMemoryOnlineEvaluator:
    async def test_evaluate_does_not_block_returns_empty_metrics(self) -> None:
        """§8 Stage 7b: evaluate() 不阻塞主路径, 立即返回。"""
        ev = InMemoryOnlineEvaluator()
        m = await ev.evaluate(
            turn_id="t-1", agent_id="a-1", tenant_id="t-1",
            engine_version="v1", query="q", answer="a",
            retrieved_context=[],
        )
        # 立即返回空 metrics (后台任务未完成)
        assert m.recall_at_k == 0.0

    async def test_background_task_writes_metrics(self) -> None:
        """§8 Stage 7b: 后台任务完成时 metrics 写入 records。"""
        ev = InMemoryOnlineEvaluator()
        ev.set_gold_evidence("t-1", [{"source_id": "doc-1"}, {"source_id": "doc-2"}])
        await ev.evaluate(
            turn_id="t-1", agent_id="a-1", tenant_id="t-1",
            engine_version="v1", query="q", answer="a",
            retrieved_context=[{"source_id": "doc-1"}, {"source_id": "doc-other"}],
        )
        # 等待后台任务完成
        await ev.wait_pending()
        rec = ev.get("t-1")
        assert rec is not None
        # Recall@5 = 1/2 (1 hit out of 2 gold)
        assert rec.metrics.recall_at_k == 0.5
        # groundedness = 1.0 (answer + 1 hit)
        assert rec.metrics.groundedness == 1.0

    async def test_no_gold_evidence_returns_zero_metrics(self) -> None:
        ev = InMemoryOnlineEvaluator()
        await ev.evaluate(
            turn_id="t-1", agent_id="a-1", tenant_id="t-1",
            engine_version="v1", query="q", answer="a",
            retrieved_context=[{"source_id": "doc-1"}],
        )
        await ev.wait_pending()
        rec = ev.get("t-1")
        assert rec.metrics.recall_at_k == 0.0
        assert rec.metrics.mrr == 0.0
        # groundedness 仍是 1.0 (有 answer, hits=0 但函数简化逻辑)
        # 注: 当前实现当无 gold 时 groundedness=1 if answer else 0
        assert rec.metrics.groundedness == 1.0

    async def test_mrr_uses_first_hit_position(self) -> None:
        ev = InMemoryOnlineEvaluator()
        ev.set_gold_evidence("t-1", [{"source_id": "doc-1"}])
        # 第一个 doc 不是 gold, 第二个是
        await ev.evaluate(
            turn_id="t-1", agent_id="a-1", tenant_id="t-1",
            engine_version="v1", query="q", answer="a",
            retrieved_context=[
                {"source_id": "doc-other"},
                {"source_id": "doc-1"},
            ],
        )
        await ev.wait_pending()
        rec = ev.get("t-1")
        # MRR = 1/2 (gold 在位置 2)
        assert rec.metrics.mrr == 0.5


# ---------------------------------------------------------------------------
# RolloutPolicy + EngineSwitch
# ---------------------------------------------------------------------------


class TestRolloutPolicy:
    def test_default_zero_percent_all_v0(self) -> None:
        sw = EngineSwitch(RolloutPolicy(rollout_percent=0))
        assert sw.pick_engine_version(agent_id="a", tenant_id="t") == "v0"

    def test_hundred_percent_all_v1(self) -> None:
        sw = EngineSwitch(RolloutPolicy(rollout_percent=100))
        assert sw.pick_engine_version(agent_id="a", tenant_id="t") == "v1"

    def test_force_v0_overrides_rollout_percent(self) -> None:
        sw = EngineSwitch(RolloutPolicy(
            rollout_percent=100,
            force_v0_agents=frozenset({"special-agent"}),
        ))
        assert sw.pick_engine_version(agent_id="special-agent", tenant_id="t") == "v0"
        # 其他仍走 v1
        assert sw.pick_engine_version(agent_id="other", tenant_id="t") == "v1"

    def test_force_v1_overrides_rollout_percent(self) -> None:
        sw = EngineSwitch(RolloutPolicy(
            rollout_percent=0,
            force_v1_tenants=frozenset({"vip-tenant"}),
        ))
        assert sw.pick_engine_version(agent_id="a", tenant_id="vip-tenant") == "v1"
        assert sw.pick_engine_version(agent_id="a", tenant_id="other") == "v0"

    def test_stable_bucket_same_input_same_output(self) -> None:
        """§8 Stage 7b: 同一 (agent, tenant) 永远落入同一 bucket。"""
        sw = EngineSwitch(RolloutPolicy(rollout_percent=50))
        a1 = sw.pick_engine_version(agent_id="agt-1", tenant_id="tnt-1")
        a2 = sw.pick_engine_version(agent_id="agt-1", tenant_id="tnt-1")
        assert a1 == a2

    def test_rollout_distribution_approximate(self) -> None:
        """100 次随机抽样, v1 比例应接近 rollout_percent。"""
        sw = EngineSwitch(RolloutPolicy(rollout_percent=30))
        # 用不同 agent_id 增加采样空间
        v1_count = sum(
            1 for i in range(100)
            if sw.pick_engine_version(agent_id=f"a-{i}", tenant_id="t-1") == "v1"
        )
        # 30% ± 10% 容差
        assert 20 <= v1_count <= 40

    def test_salt_changes_bucket(self) -> None:
        """不同 salt 应给出不同的分桶。"""
        sw1 = EngineSwitch(RolloutPolicy(rollout_percent=50, salt="salt-a"))
        sw2 = EngineSwitch(RolloutPolicy(rollout_percent=50, salt="salt-b"))
        results = [
            (sw1.pick_engine_version(agent_id=f"a-{i}", tenant_id="t"),
             sw2.pick_engine_version(agent_id=f"a-{i}", tenant_id="t"))
            for i in range(20)
        ]
        # 至少有一些不一致 (分桶分布不同)
        diffs = sum(1 for a, b in results if a != b)
        assert diffs > 5  # 至少 25% 不一致


# ---------------------------------------------------------------------------
# persist_result 节点: 异步触发 evaluator
# ---------------------------------------------------------------------------


class TestPersistResultTriggersEvaluator:
    def test_no_evaluator_no_error(self) -> None:
        """未注入 evaluator 时 persist_result 不抛异常。"""
        nodes.set_default_usage_tracker(UsageTracker())
        out = nodes.persist_result({
            "turn_id": "t-1",
            "tenant_id": "t-1",
            "messages": [{"role": "user", "content": "test"}],
            "result": {"final_message": "ok"},
        })
        assert "usage" in out or out == {}

    def test_evaluator_receives_turn_data(self) -> None:
        """§8 Stage 7b: persist_result 触发 evaluator 收集 turn 指标。

        mock 用 sync evaluate (Record 立即发生), 避免 event loop 复杂度。
        """
        from qzdap_agent_runtime.evaluation import EvalMetric

        class _SyncMockEvaluator:
            """同步 evaluate: 立即记录, 不创建 coroutine。"""

            def __init__(self) -> None:
                self.calls: list[dict] = []

            def evaluate(self, **kwargs) -> EvalMetric:
                self.calls.append(kwargs)
                return EvalMetric(groundedness=1.0)

        tracker = UsageTracker()
        tracker.start("t-1", tenant_id="t-1", workspace_id="w-1",
                     user_id="u-1", agent_id="agt-1", agent_version="v1",
                     model_version="m1")
        tracker.add_tokens("t-1", input_tokens=100, output_tokens=50)

        evaluator = _SyncMockEvaluator()
        nodes.set_default_usage_tracker(tracker)
        nodes.set_default_evaluator(evaluator)  # type: ignore[arg-type]

        out = nodes.persist_result({
            "turn_id": "t-1",
            "agent_id": "agt-1",
            "tenant_id": "t-1",
            "workspace_id": "w-1",
            "user_id": "u-1",
            "agent_version": "v1",
            "model_version": "m1",
            "messages": [{"role": "user", "content": "what is RAG?"}],
            "result": {"final_message": "RAG is retrieval-augmented generation"},
            "knowledge_hits": [{"source_id": "doc-1"}],
        })
        # usage 写回
        assert "usage" in out
        # evaluator 同步记录调用
        assert len(evaluator.calls) == 1
        call = evaluator.calls[0]
        assert call["turn_id"] == "t-1"
        assert call["agent_id"] == "agt-1"
        assert call["tenant_id"] == "t-1"
        assert call["query"] == "what is RAG?"
        assert "RAG" in call["answer"]