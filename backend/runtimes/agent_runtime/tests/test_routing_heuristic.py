"""Tests for §2.5 阻塞 6 — Deep Agents 启发式 task_kind 分类器。

Stage 4 退出条件（§2.5 阻塞 6 验证）：

- `classify_task_kind_heuristic` 单测覆盖 5 类输入（deep_research=true /
  长上下文 / 关键词 deep / 关键词 code / 默认 fallback），返回值均为合法 TaskKind。
- `route.deep_task=true` 时进入 `deep_agent_plan`，否则进入 `agent` 单 ReAct 循环。
"""

from __future__ import annotations

import pytest

from qzdap_agent_runtime.graph import (
    AgentRouteConfig,
    TaskKind,
    classify_task_kind_heuristic,
    is_deep_task,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def default_config() -> AgentRouteConfig:
    return AgentRouteConfig(agent_id="agt_default", deep_research=False)


# ---------------------------------------------------------------------------
# 5 类输入场景（§2.5 阻塞 6 验证要求）
# ---------------------------------------------------------------------------


class TestClassifyTaskKindHeuristic:
    """5 类输入 → 5 类预期输出。"""

    def test_rule1_deep_research_flag_wins(
        self, default_config: AgentRouteConfig
    ) -> None:
        """规则 1：agent.deep_research=true 优先（即使消息很短）。"""
        cfg = AgentRouteConfig(agent_id="agt_deep", deep_research=True)
        kind = classify_task_kind_heuristic(
            message_count=1,
            tools_count=1,
            message_text="hello",
            agent_config=cfg,
        )
        assert kind is TaskKind.DEEP_RESEARCH
        assert is_deep_task(kind) is True

    def test_rule2_long_context_and_many_tools(
        self, default_config: AgentRouteConfig
    ) -> None:
        """规则 2：message_count > 20 且 tools_count > 5 → MULTI_STEP_CODE。"""
        kind = classify_task_kind_heuristic(
            message_count=21,
            tools_count=6,
            message_text="继续",
            agent_config=default_config,
        )
        assert kind is TaskKind.MULTI_STEP_CODE
        assert is_deep_task(kind) is True

    def test_rule2_threshold_boundary(
        self, default_config: AgentRouteConfig
    ) -> None:
        """规则 2 边界：message_count=20 或 tools_count=5 不触发。"""
        # message_count=20（不 > 20）→ 不触发 rule 2
        kind = classify_task_kind_heuristic(
            message_count=20,
            tools_count=10,
            message_text="继续",
            agent_config=default_config,
        )
        assert kind is TaskKind.SIMPLE_QA

        # tools_count=5（不 > 5）→ 不触发 rule 2
        kind = classify_task_kind_heuristic(
            message_count=30,
            tools_count=5,
            message_text="继续",
            agent_config=default_config,
        )
        assert kind is TaskKind.SIMPLE_QA

    def test_rule3_keyword_deep_chinese(
        self, default_config: AgentRouteConfig
    ) -> None:
        """规则 3：中文 deep 关键词 → DEEP_RESEARCH。"""
        for keyword in ("研究", "调研", "对比", "分析", "综述"):
            kind = classify_task_kind_heuristic(
                message_count=5,
                tools_count=3,
                message_text=f"帮我{kw_safe(keyword)}一下这个项目",
                agent_config=default_config,
            )
            assert kind is TaskKind.DEEP_RESEARCH, f"keyword={keyword}"

    def test_rule3_keyword_deep_english(
        self, default_config: AgentRouteConfig
    ) -> None:
        """规则 3：英文 deep 关键词（大小写不敏感）→ DEEP_RESEARCH。"""
        for keyword in ("research", "compare", "investigate", "survey"):
            kind = classify_task_kind_heuristic(
                message_count=5,
                tools_count=3,
                message_text=f"Please {keyword.upper()} this topic",
                agent_config=default_config,
            )
            assert kind is TaskKind.DEEP_RESEARCH, f"keyword={keyword}"

    def test_rule3_keyword_code_chinese(
        self, default_config: AgentRouteConfig
    ) -> None:
        """规则 3：中文 code 关键词 → MULTI_STEP_CODE。"""
        for keyword in ("写代码", "实现", "重构", "迁移"):
            kind = classify_task_kind_heuristic(
                message_count=5,
                tools_count=3,
                message_text=f"帮我{kw_safe(keyword)}这个模块",
                agent_config=default_config,
            )
            assert kind is TaskKind.MULTI_STEP_CODE, f"keyword={keyword}"

    def test_rule3_keyword_code_english(
        self, default_config: AgentRouteConfig
    ) -> None:
        """规则 3：英文 code 关键词 → MULTI_STEP_CODE。"""
        for keyword in ("refactor", "implement", "migrate", "rewrite", "build"):
            kind = classify_task_kind_heuristic(
                message_count=5,
                tools_count=3,
                message_text=f"Please {keyword} this module",
                agent_config=default_config,
            )
            assert kind is TaskKind.MULTI_STEP_CODE, f"keyword={keyword}"

    def test_rule3_deep_keyword_priority_over_code(
        self, default_config: AgentRouteConfig
    ) -> None:
        """规则 3：deep 关键词优先于 code 关键词（出现在 list 中时分类）。"""
        # 同时含 deep 与 code 关键词 → deep 胜出
        kind = classify_task_kind_heuristic(
            message_count=5,
            tools_count=3,
            message_text="帮我调研并重构这个模块",
            agent_config=default_config,
        )
        assert kind is TaskKind.DEEP_RESEARCH

    def test_rule4_default_fallback(
        self, default_config: AgentRouteConfig
    ) -> None:
        """规则 4：默认 fallback → SIMPLE_QA（不允许 None）。"""
        kind = classify_task_kind_heuristic(
            message_count=3,
            tools_count=2,
            message_text="今天天气怎么样",
            agent_config=default_config,
        )
        assert kind is TaskKind.SIMPLE_QA
        assert is_deep_task(kind) is False

    def test_rule4_empty_message(
        self, default_config: AgentRouteConfig
    ) -> None:
        """规则 4：空消息 → SIMPLE_QA（不允许 None / 不允许抛异常）。"""
        kind = classify_task_kind_heuristic(
            message_count=0,
            tools_count=0,
            message_text="",
            agent_config=default_config,
        )
        assert kind is TaskKind.SIMPLE_QA


# ---------------------------------------------------------------------------
# fallback 约定（§2.5 阻塞 6 决议）
# ---------------------------------------------------------------------------


class TestFallbackContract:
    """fallback 路径必须满足的硬约束。"""

    def test_no_none_returned(self, default_config: AgentRouteConfig) -> None:
        """不允许返回 None：覆盖 50 组随机参数。"""
        for msg_count in (0, 1, 5, 20, 21, 100):
            for tools_count in (0, 1, 5, 6, 50):
                for text in ("", "hello", "重构代码", "research this", "对比分析"):
                    kind = classify_task_kind_heuristic(
                        message_count=msg_count,
                        tools_count=tools_count,
                        message_text=text,
                        agent_config=default_config,
                    )
                    assert kind is not None
                    assert isinstance(kind, TaskKind)

    def test_no_exception_raised(self, default_config: AgentRouteConfig) -> None:
        """不允许抛异常：覆盖异常输入。"""
        # 负数、空字符串、特殊字符
        for msg_count in (-1, 0, 1):
            for tools_count in (-1, 0, 1):
                for text in ("", " ", "\n", "🔥 emoji"):
                    kind = classify_task_kind_heuristic(
                        message_count=msg_count,
                        tools_count=tools_count,
                        message_text=text,
                        agent_config=default_config,
                    )
                    assert isinstance(kind, TaskKind)

    def test_is_deep_task_is_bool(self) -> None:
        """is_deep_task 必须返回纯 bool（不允许 Optional[bool]）。"""
        for kind in TaskKind:
            result = is_deep_task(kind)
            assert isinstance(result, bool)
            if kind is TaskKind.SIMPLE_QA:
                assert result is False
            else:
                assert result is True


# ---------------------------------------------------------------------------
# TaskKind 枚举自身
# ---------------------------------------------------------------------------


class TestTaskKindEnum:
    """TaskKind 枚举值与 i18n key 稳定性。"""

    def test_task_kind_values_distinct(self) -> None:
        assert len({k.value for k in TaskKind}) == len(list(TaskKind))

    def test_task_kind_includes_required_kinds(self) -> None:
        """必须包含 §2.5 阻塞 6 决议指定的 4 个枚举值。"""
        assert hasattr(TaskKind, "SIMPLE_QA")
        assert hasattr(TaskKind, "DEEP_RESEARCH")
        assert hasattr(TaskKind, "MULTI_STEP_CODE")
        assert hasattr(TaskKind, "DATA_INVESTIGATION")

    def test_task_kind_is_str_subclass(self) -> None:
        """TaskKind 必须为 str 子类，便于序列化到 state。"""
        assert isinstance(TaskKind.SIMPLE_QA, str)
        assert TaskKind.SIMPLE_QA == "SIMPLE_QA"


# ---------------------------------------------------------------------------
# helper
# ---------------------------------------------------------------------------


def kw_safe(s: str) -> str:
    """CI 环境无关的占位替换：把测试用关键词回写（避免 import 时副作用）。"""
    return s