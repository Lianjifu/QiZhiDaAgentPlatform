"""``TaskClassifier`` —— **这一轮是什么任务** ✓（含置信度 ✓）。

依据：Agent 方案 §4.1（每步都要知道 task_kind ✓）、§8.1
（``agent_router/classifier.py`` ✓）。

⚠️ **从 ``graph/routing.py`` 迁来** ✓（A-03 ✓）—— 分类器归**专家路由**这一侧
✓（它不是「图节点」的附属品 ✓ —— 节点只是用它的一个消费者 ✓）。

⚠️ **启发式起步** ✓（决策 #3 的规则版 ✓）—— 将来换小模型分类器时**只换实现**
✓（接口不变 ✓）。

⚠️ **分类失败要能降级** ✓ —— 返回值**永远是一个合法分类** ✓（不允许
``None`` ✓ —— 调用方不必处理「没分类出来」这种状态 ✗✗）。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

# ---------------------------------------------------------------------------
# 类型定义
# ---------------------------------------------------------------------------


class TaskKind(str, Enum):
    """会话 turn 的任务类型，决定是否启用 Deep Agents 路径。

    `route.deep_task` 计算规则：
        deep_task = kind in {DEEP_RESEARCH, MULTI_STEP_CODE, DATA_INVESTIGATION}
    """

    SIMPLE_QA = "SIMPLE_QA"
    DEEP_RESEARCH = "DEEP_RESEARCH"
    MULTI_STEP_CODE = "MULTI_STEP_CODE"
    DATA_INVESTIGATION = "DATA_INVESTIGATION"


_DEEP_KINDS: frozenset[TaskKind] = frozenset(
    {TaskKind.DEEP_RESEARCH, TaskKind.MULTI_STEP_CODE, TaskKind.DATA_INVESTIGATION}
)


@dataclass(frozen=True, slots=True)
class AgentRouteConfig:
    """agent catalog 提供的路由配置（与 §5.5 联动）。

    `deep_research` 是用户显式声明的 deep path 开关；分类器不覆盖此字段。
    """

    agent_id: str
    deep_research: bool = False


@dataclass(frozen=True, slots=True)
class TaskClassification:
    """一次分类的结果 ✓（**类型 + 置信度** ✓）。

    ⚠️ **置信度不是概率** ✓ —— 它是「这条规则有多强」的刻度 ✓（启发式没有
    概率语义 ✗✗ —— 别把它当校准过的概率用 ✗）。
    """

    kind: TaskKind
    confidence: float
    reason: str = ""


# ---------------------------------------------------------------------------
# 关键词词典（启发式触发器）
# ---------------------------------------------------------------------------

#: 触发 DEEP_RESEARCH 的中文 + 英文关键词
_KEYWORDS_DEEP: tuple[str, ...] = (
    "研究",
    "调研",
    "对比",
    "分析",
    "综述",
    "research",
    "compare",
    "investigate",
    "investigation",
    "survey",
)

#: 触发 MULTI_STEP_CODE 的中文 + 英文关键词
_KEYWORDS_CODE: tuple[str, ...] = (
    "写代码",
    "实现",
    "重构",
    "迁移",
    "refactor",
    "implement",
    "migrate",
    "rewrite",
    "build",
)

#: 各类命中的置信度 ✓（启发式的刻度 ✓ —— 不是概率 ✗）。
_CONFIDENCE_EXPLICIT = 1.0
_CONFIDENCE_RULE = 0.6
_CONFIDENCE_LONG_CONTEXT = 0.7
_CONFIDENCE_FALLBACK = 0.3


# ---------------------------------------------------------------------------
# 分类器
# ---------------------------------------------------------------------------


class TaskClassifier:
    """**启发式分类器** ✓ —— 零成本 ✓、确定性强 ✓。

    ⚠️ **本类是唯一实现** ✓ —— 模块级的 ``classify_task_kind_heuristic``
    只是它的函数形态 ✓（不多一份逻辑 ✗✗）。
    """

    def classify(
        self,
        *,
        message_count: int,
        tools_count: int,
        message_text: str,
        agent_config: AgentRouteConfig,
    ) -> TaskClassification:
        """分类 ✓ —— **永远返回一个合法分类** ✓（§2.5 阻塞 6 ✓）。

        规则（按优先级）：

        1. ``agent_config.deep_research == true`` → ``DEEP_RESEARCH``
           （用户显式声明优先 ✓ —— 分类器不覆盖它 ✗）。
        2. ``(message_count > 20) ∧ (tools_count > 5)`` → ``MULTI_STEP_CODE``
           （长上下文 + 多工具 ✓ —— 保守归类 ✓）。
        3. 关键词匹配 ✓：deep 关键词 → ``DEEP_RESEARCH`` ✓；code 关键词 →
           ``MULTI_STEP_CODE`` ✓。
        4. 默认 fallback → ``SIMPLE_QA`` ✓。
        """
        if agent_config.deep_research:
            return TaskClassification(
                kind=TaskKind.DEEP_RESEARCH,
                confidence=_CONFIDENCE_EXPLICIT,
                reason="用户显式声明了 deep path",
            )
        if message_count > 20 and tools_count > 5:
            return TaskClassification(
                kind=TaskKind.MULTI_STEP_CODE,
                confidence=_CONFIDENCE_LONG_CONTEXT,
                reason="长上下文 + 多工具",
            )
        text_lower = message_text.lower()
        if any(keyword in text_lower for keyword in _KEYWORDS_DEEP):
            return TaskClassification(
                kind=TaskKind.DEEP_RESEARCH,
                confidence=_CONFIDENCE_RULE,
                reason="命中 deep 关键词",
            )
        if any(keyword in text_lower for keyword in _KEYWORDS_CODE):
            return TaskClassification(
                kind=TaskKind.MULTI_STEP_CODE,
                confidence=_CONFIDENCE_RULE,
                reason="命中 code 关键词",
            )
        return TaskClassification(
            kind=TaskKind.SIMPLE_QA,
            confidence=_CONFIDENCE_FALLBACK,
            reason="默认 fallback",
        )


#: 默认分类器 ✓（**无状态** ✓ —— 多线程共用一个 ✓）。
DEFAULT_CLASSIFIER = TaskClassifier()


def classify_task_kind_heuristic(
    *,
    message_count: int,
    tools_count: int,
    message_text: str,
    agent_config: AgentRouteConfig,
) -> TaskClassification:
    """启发式分类的**函数形态** ✓（§2.5 阻塞 6 的原入口 ✓）。

    ⚠️ **返回值多了置信度** ✓（A-03 ✓）—— 旧的调用方只读 ``kind`` ✓。
    """
    return DEFAULT_CLASSIFIER.classify(
        message_count=message_count,
        tools_count=tools_count,
        message_text=message_text,
        agent_config=agent_config,
    )


def is_deep_task(kind: TaskKind) -> bool:
    """根据 `TaskKind` 计算 `route.deep_task`。

    等价于 `kind in {DEEP_RESEARCH, MULTI_STEP_CODE, DATA_INVESTIGATION}`，
    提供显式函数以便节点代码可读性。
    """
    return kind in _DEEP_KINDS


__all__ = [
    "DEFAULT_CLASSIFIER",
    "AgentRouteConfig",
    "TaskClassification",
    "TaskClassifier",
    "TaskKind",
    "classify_task_kind_heuristic",
    "is_deep_task",
]
