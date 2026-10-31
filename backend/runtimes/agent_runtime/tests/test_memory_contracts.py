"""Memory 层的**契约** —— Stage 0 新建的骨架 ✓。

依据：Memory 方案 §10.1（A1–A3 的契约 ✓）、§3.2（作用域 ✓）、
§4.2（抽取 ✓）、§4.3（闸门 ✓）、§7（C6 策略绑定 ✓）。

⚠️ **这些只是契约** ✓ —— 实现归 Stage 2 / Stage 3 ✓；这里断言的是
**形状与规则** ✓（规则错了，实现就会错 ✗✗）。
"""

from __future__ import annotations

from qzdap_agent_runtime.memory.extraction import FactCandidate
from qzdap_agent_runtime.memory.policy import MemoryPolicy, PolicyBinding
from qzdap_agent_runtime.memory.redaction import RedactionResult
from qzdap_agent_runtime.memory.retrieval import RetrievalOutcome
from qzdap_agent_runtime.memory.scope import MemoryScope, scope_of_layer
from qzdap_agent_runtime.memory.writer import WriteOutcome


class TestScope:
    def test_layers_map_to_scopes(self) -> None:
        # ⚠️ **只有 L2 了** ✓ —— L1 退役（M-46 ✓）/ L3 退役（M-47 ✓）✓。
        assert scope_of_layer("l2") is MemoryScope.USER

    def test_an_unknown_layer_falls_back_to_the_narrowest(self) -> None:
        """未知层级 → **用户级** ✓（最窄 ✓）—— 放宽可见性会泄漏 ✗✗。"""
        assert scope_of_layer("l9") is MemoryScope.USER
        assert scope_of_layer("") is MemoryScope.USER


class TestPolicy:
    def test_the_binding_parses_the_agent_config(self) -> None:
        policy = PolicyBinding(
            {
                "enabled": False,
                "scope": "workspace",
                "policyLabel": "长期记忆",
                "autoSummarize": True,
                "retentionDays": 30,
            }
        ).to_policy()
        assert policy.enabled is False
        assert policy.scope is MemoryScope.WORKSPACE
        assert policy.policy_label == "长期记忆"
        assert policy.auto_summarize is True
        assert policy.retention_days == 30

    def test_a_missing_binding_defaults_to_user_scope(self) -> None:
        policy = PolicyBinding({}).to_policy()
        assert policy.enabled is True
        assert policy.scope is MemoryScope.USER

    def test_an_unknown_scope_is_narrowed(self) -> None:
        """认不出来的 scope → **用户级** ✓（不猜 ✓）。"""
        policy = PolicyBinding({"scope": "everything"}).to_policy()
        assert policy.scope is MemoryScope.USER

    def test_the_default_policy_is_user_scoped(self) -> None:
        assert MemoryPolicy().scope is MemoryScope.USER


class TestShapes:
    def test_a_fact_candidate_carries_its_confidence(self) -> None:
        candidate = FactCandidate(content="张三的报销额度是五千元", source="rule", confidence=0.7)
        assert candidate.source == "rule"
        assert 0.0 < candidate.confidence < 1.0

    def test_a_blocked_redaction_names_the_kind(self) -> None:
        result = RedactionResult(blocked=True, kinds=("phone",), reason="手机号")
        assert result.blocked is True
        assert "phone" in result.kinds

    def test_an_abstained_retrieval_is_distinguishable(self) -> None:
        """「没找到够格的」要与「没有相关知识」**区分得开** ✓。"""
        outcome = RetrievalOutcome(hits=[], abstained=True)
        assert outcome.abstained is True
        assert outcome.hits == []

    def test_a_write_outcome_separates_rejections(self) -> None:
        outcome = WriteOutcome(written=[{"id": "1"}], rejected=[{"content": "手机号"}])
        assert len(outcome.written) == 1
        assert len(outcome.rejected) == 1
