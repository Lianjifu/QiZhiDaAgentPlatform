"""**⑧ Agent Router** —— 专家 Agent 的选择 ✓（本包只管「交给谁」✓）。

依据：Agent 方案 §4（Agent Router ✓）、§4.1（选哪个专家 ✓）、§4.2
（专家配置即绑定来源 ✓）。

⚠️ **本层不做「选模型 / 选工具」** ✓（决策 #4 ✓）—— 那些是 ⑨ Execution 的
**取值**职责 ✓（§5.2 / §5.3 ✓）。
"""

from .classifier import (
    DEFAULT_CLASSIFIER,
    AgentRouteConfig,
    TaskClassification,
    TaskClassifier,
    TaskKind,
    classify_task_kind_heuristic,
    is_deep_task,
)

__all__ = [
    "DEFAULT_CLASSIFIER",
    "AgentRouteConfig",
    "TaskClassification",
    "TaskClassifier",
    "TaskKind",
    "classify_task_kind_heuristic",
    "is_deep_task",
]
