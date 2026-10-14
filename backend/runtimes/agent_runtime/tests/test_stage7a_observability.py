"""Tests for Stage 7a: UsageTracker + CostAttribution + DegradedCounter."""

from __future__ import annotations

import pytest

from qzdap_agent_runtime.observability import (
    CostAttribution,
    DegradedCounter,
    DegradedKind,
    InMemoryCostAttribution,
    UsageRecord,
    UsageTracker,
)


# ---------------------------------------------------------------------------
# Protocol duck-typing
# ---------------------------------------------------------------------------


def test_cost_attribution_satisfies_protocol() -> None:
    assert isinstance(InMemoryCostAttribution(), CostAttribution)


# ---------------------------------------------------------------------------
# DegradedCounter (§8 Stage 7a: Prometheus-style counter)
# ---------------------------------------------------------------------------


class TestDegradedCounter:
    def test_initial_zero(self) -> None:
        c = DegradedCounter()
        for kind in DegradedKind:
            assert c.value(kind) == 0

    def test_inc_specific_kind(self) -> None:
        c = DegradedCounter()
        c.inc(DegradedKind.RECALL)
        c.inc(DegradedKind.RECALL)
        c.inc(DegradedKind.LANGSMITH)
        assert c.value(DegradedKind.RECALL) == 2
        assert c.value(DegradedKind.LANGSMITH) == 1
        assert c.value(DegradedKind.COMPACTION) == 0

    def test_inc_by_n(self) -> None:
        c = DegradedCounter()
        c.inc(DegradedKind.COST_ATTRIBUTION, n=5)
        assert c.value(DegradedKind.COST_ATTRIBUTION) == 5

    def test_snapshot_returns_all(self) -> None:
        c = DegradedCounter()
        c.inc(DegradedKind.RECALL)
        c.inc(DegradedKind.LANGSMITH)
        snap = c.snapshot()
        assert snap["recall"] == 1
        assert snap["langsmith"] == 1
        # 其他是 0
        assert snap["compaction"] == 0
        assert snap["cost_attribution"] == 0

    def test_export_prometheus_format(self) -> None:
        """§8 Stage 7a: qzdap_observability_degraded_total{degraded=...} 格式。"""
        c = DegradedCounter()
        c.inc(DegradedKind.RECALL, n=3)
        c.inc(DegradedKind.LANGSMITH, n=1)
        out = c.export_prometheus()
        # 必须包含 4 类
        assert 'qzdap_observability_degraded_total{degraded="recall"} 3' in out
        assert 'qzdap_observability_degraded_total{degraded="langsmith"} 1' in out
        assert 'qzdap_observability_degraded_total{degraded="compaction"} 0' in out
        assert 'qzdap_observability_degraded_total{degraded="cost_attribution"} 0' in out
        # 必须有 HELP + TYPE 行
        assert "# HELP qzdap_observability_degraded_total" in out
        assert "# TYPE qzdap_observability_degraded_total counter" in out


# ---------------------------------------------------------------------------
# UsageTracker (§5.10)
# ---------------------------------------------------------------------------


class TestUsageTracker:
    def test_start_initializes_record(self) -> None:
        t = UsageTracker()
        t.start("turn-1", tenant_id="t-1", workspace_id="w-1",
               user_id="u-1", agent_id="agt-1", agent_version="v1",
               model_version="m1")
        rec = t.get("turn-1")
        assert rec is not None
        assert rec.tenant_id == "t-1"
        assert rec.cost_unknown is True
        assert rec.cost_usd is None

    def test_add_tokens_accumulates(self) -> None:
        t = UsageTracker()
        t.start("t-1", tenant_id="t", workspace_id="w", user_id="u",
               agent_id="a", agent_version="v", model_version="m")
        t.add_tokens("t-1", input_tokens=100, output_tokens=50)
        t.add_tokens("t-1", input_tokens=200, output_tokens=80, cache_tokens=30)
        rec = t.get("t-1")
        assert rec.input_tokens == 300
        assert rec.output_tokens == 130
        assert rec.cache_tokens == 30

    def test_set_cost_overrides(self) -> None:
        t = UsageTracker()
        t.start("t-1", tenant_id="t", workspace_id="w", user_id="u",
               agent_id="a", agent_version="v", model_version="m")
        t.set_cost("t-1", cost_usd=0.05, retry_count=2)
        rec = t.get("t-1")
        assert rec.cost_usd == 0.05
        assert rec.cost_unknown is False
        assert rec.retry_count == 2

    def test_mark_cost_unknown_increments_degraded(self) -> None:
        """§5.10: 未知 cost 必须显式标记 + cost_attribution_degraded 计数。"""
        t = UsageTracker()
        t.start("t-1", tenant_id="t", workspace_id="w", user_id="u",
               agent_id="a", agent_version="v", model_version="m")
        t.mark_cost_unknown("t-1")
        rec = t.get("t-1")
        assert rec.cost_unknown is True
        assert t.degraded.value(DegradedKind.COST_ATTRIBUTION) == 1

    def test_add_tokens_silently_ignores_unknown_turn(self) -> None:
        """未 start 的 turn_id 必须静默忽略 (Stage 1 fake 兼容)。"""
        t = UsageTracker()
        t.add_tokens("never-initialized", input_tokens=100)  # 不抛
        assert t.get("never-initialized") is None

    def test_to_usage_event_dict_has_all_6_dims(self) -> None:
        """§5.10: UsageChunk 必带 6 维度 + tokens。"""
        t = UsageTracker()
        t.start("t-1", tenant_id="t-1", workspace_id="w-1", user_id="u-1",
               agent_id="agt-1", agent_version="v1", model_version="m1")
        t.add_tokens("t-1", input_tokens=100, output_tokens=50, cache_tokens=10)
        t.set_cost("t-1", cost_usd=0.001, retry_count=1)
        rec = t.get("t-1")
        d = rec.to_usage_event_dict()
        # 6 维度必填
        for required in ("tenant_id", "workspace_id", "user_id",
                         "agent_id", "agent_version", "model_version"):
            assert required in d, f"missing {required}"
        # tokens
        assert d["input_tokens"] == 100
        assert d["output_tokens"] == 50
        assert d["cache_tokens"] == 10
        assert d["cost_usd"] == 0.001
        assert d["cost_unknown"] is False
        assert d["retry_count"] == 1


# ---------------------------------------------------------------------------
# InMemoryCostAttribution
# ---------------------------------------------------------------------------


class TestInMemoryCostAttribution:
    def test_record_unknown_cost_skipped(self) -> None:
        ca = InMemoryCostAttribution()
        rec = UsageRecord(
            tenant_id="t", workspace_id="w", user_id="u",
            agent_id="a", agent_version="v", model_version="m",
            cost_usd=None, cost_unknown=True,
        )
        ca.record(rec)
        assert ca.by_tenant("t") == 0.0

    def test_record_known_cost_aggregates_by_tenant(self) -> None:
        ca = InMemoryCostAttribution()
        rec = UsageRecord(
            tenant_id="t-1", workspace_id="w-1", user_id="u-1",
            agent_id="a", agent_version="v", model_version="m",
            cost_usd=0.05, cost_unknown=False,
        )
        ca.record(rec)
        ca.record(rec)
        rec2 = UsageRecord(
            tenant_id="t-1", workspace_id="w-1", user_id="u-2",
            agent_id="a", agent_version="v", model_version="m",
            cost_usd=0.10, cost_unknown=False,
        )
        ca.record(rec2)
        rec3 = UsageRecord(
            tenant_id="t-2", workspace_id="w-1", user_id="u-1",
            agent_id="a", agent_version="v", model_version="m",
            cost_usd=0.20, cost_unknown=False,
        )
        ca.record(rec3)
        # t-1 总计 0.05*2 + 0.10 = 0.20
        assert ca.by_tenant("t-1") == 0.20
        # t-2 总计 0.20
        assert ca.by_tenant("t-2") == 0.20

    def test_snapshot_includes_calls(self) -> None:
        ca = InMemoryCostAttribution()
        rec = UsageRecord(
            tenant_id="t", workspace_id="w", user_id="u",
            agent_id="a", agent_version="v", model_version="m",
            cost_usd=0.05, cost_unknown=False,
        )
        ca.record(rec)
        ca.record(rec)
        snap = ca.snapshot()
        key = ("t", "w", "u", "a")
        assert snap[key]["cost_usd"] == 0.10
        assert snap[key]["calls"] == 2


# ---------------------------------------------------------------------------
# §8 Stage 7a 退出条件: usage 必带 6 维度
# ---------------------------------------------------------------------------


class TestUsageChunkRequiredDims:
    def test_to_usage_event_dict_compliance(self) -> None:
        """§5.10 + §8 Stage 7a 退出条件: UsageChunk 携带完整 6 维度。"""
        rec = UsageRecord(
            tenant_id="t", workspace_id="w", user_id="u",
            agent_id="a", agent_version="v", model_version="m",
        )
        d = rec.to_usage_event_dict()
        # 6 维度 + tokens + cost 字段全有
        required_keys = {
            "tenant_id", "workspace_id", "user_id",
            "agent_id", "agent_version", "model_version",
            "input_tokens", "output_tokens", "cache_tokens",
            "cost_usd", "cost_unknown", "retry_count",
        }
        assert required_keys.issubset(d.keys())