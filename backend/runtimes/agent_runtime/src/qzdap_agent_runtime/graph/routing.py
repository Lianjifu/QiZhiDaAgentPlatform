"""Routing 节点辅助逻辑：task_kind 分类 + 路径决策（§2.5 阻塞 6）。

Stage 4 范围内仅实现 `classify_task_kind_heuristic`（纯规则 fallback）。
Stage 6b 再由 docs/refactor/deepagents-classifier-spec.md 定义的
小模型分类器替换本实现。

fallback 约定（§2.5 阻塞 6 决议）：

- `classify_task_kind_heuristic` 必须返回 `TaskKind` 枚举之一，不允许 `None`。
- 分类超时（Stage 6b）必须回退 `TaskKind.SIMPLE_QA`，不允许回落模型响应。
- `route.deep_task` 必须是 `bool`，不允许 `Optional[bool]` 三态。
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


# ---------------------------------------------------------------------------
# 关键词词典（启发式触发器）
# ---------------------------------------------------------------------------

# 触发 DEEP_RESEARCH 的中文 + 英文关键词
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

# 触发 MULTI_STEP_CODE 的中文 + 英文关键词
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


# ---------------------------------------------------------------------------
# 主函数
# ---------------------------------------------------------------------------


def classify_task_kind_heuristic(
    *,
    message_count: int,
    tools_count: int,
    message_text: str,
    agent_config: AgentRouteConfig,
) -> TaskKind:
    """按 §5.5 三条规则分类 task kind。

    规则（按优先级）：

    1. `agent_config.deep_research == true` → `DEEP_RESEARCH`（用户显式声明优先）。
    2. `(message_count > 20) ∧ (tools_count > 5)` → `MULTI_STEP_CODE`
       （长上下文 + 多工具，保守归类）。
    3. 关键词匹配：含 deep 关键词 → `DEEP_RESEARCH`；含 code 关键词 → `MULTI_STEP_CODE`。
    4. 默认 fallback → `SIMPLE_QA`。

    Args:
        message_count: 当前 session 的消息数（含 system / user / assistant / tool）。
        tools_count: agent 注册的工具总数（白名单 + runtime tools）。
        message_text: 当前 turn 用户输入文本（小写化后内部处理）。
        agent_config: agent catalog 提供的路由配置。

    Returns:
        `TaskKind` 枚举值之一；**不允许返回 `None` 或抛异常**。
    """
    # 规则 1：用户显式声明（不可被分类器覆盖）
    if agent_config.deep_research:
        return TaskKind.DEEP_RESEARCH

    # 规则 2：长上下文 + 多工具
    if message_count > 20 and tools_count > 5:
        return TaskKind.MULTI_STEP_CODE

    # 规则 3：关键词匹配（对 message_text 做小写化 + 大小写不敏感匹配）
    text_lower = message_text.lower()
    if any(keyword in text_lower for keyword in _KEYWORDS_DEEP):
        return TaskKind.DEEP_RESEARCH
    if any(keyword in text_lower for keyword in _KEYWORDS_CODE):
        return TaskKind.MULTI_STEP_CODE

    # 规则 4：默认 fallback（必须返回合法枚举，不允许 None）
    return TaskKind.SIMPLE_QA


def is_deep_task(kind: TaskKind) -> bool:
    """根据 `TaskKind` 计算 `route.deep_task`。

    等价于 `kind in {DEEP_RESEARCH, MULTI_STEP_CODE, DATA_INVESTIGATION}`，
    提供显式函数以便节点代码可读性。
    """
    return kind in _DEEP_KINDS


__all__ = [
    "AgentRouteConfig",
    "TaskKind",
    "classify_task_kind_heuristic",
    "is_deep_task",
]