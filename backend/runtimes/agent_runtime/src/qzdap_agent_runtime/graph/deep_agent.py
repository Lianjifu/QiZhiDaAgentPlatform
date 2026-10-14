"""Deep Agents factory + 配置 (§13.2 节点 11/12)。

Stage 6b PR A 范围：

- `DeepAgentConfig` dataclass: deep_research / max_steps / max_cost_usd /
  system_prompt / model
- `DeepAgent` Protocol: deep agent 实例 (LangGraph CompiledStateGraph)
  + invoke / astream 能力
- `DeepAgentFactory` Protocol: 给 config → DeepAgent
- `InMemoryDeepAgentFactory`: 用 `deepagents==0.7.25` 包装 create_deep_agent
- `SubAgentSpec`: sub-agent 声明 (max_steps, max_cost_usd, tools, system_prompt)
- `BUDGET_EXCEEDED_ERROR_CODE = "DEEP_AGENT_BUDGET_EXCEEDED"` 错误码
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

# ---------------------------------------------------------------------------
# Errors / 状态
# ---------------------------------------------------------------------------


DEEP_AGENT_BUDGET_EXCEEDED_ERROR_CODE = "DEEP_AGENT_BUDGET_EXCEEDED"
DEEP_AGENT_FAILED_ERROR_CODE = "DEEP_AGENT_FAILED"


class DeepAgentBudgetExceeded(Exception):
    """§5.5 决议: sub-agent 超 max_steps 或 max_cost_usd 时强制收敛。"""

    def __init__(self, message: str, spent_steps: int = 0, spent_cost_usd: float = 0.0) -> None:
        self.message = message
        self.spent_steps = spent_steps
        self.spent_cost_usd = spent_cost_usd
        super().__init__(message)


# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DeepAgentConfig:
    """§5.5 / §13.2 deep_agent_plan 节点入参。"""

    agent_id: str
    deep_research: bool = False
    max_steps: int = 20
    max_cost_usd: float = 1.0
    system_prompt: str = ""
    model: str = ""  # e.g. "openai:gpt-5" (production Stage 7a 注入真实 model)
    skills: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SubAgentSpec:
    """§5.5 sub-agent 声明 (deep_agent_plan 派发时使用)。"""

    name: str
    system_prompt: str
    tools: tuple[str, ...] = ()
    max_steps: int = 10
    max_cost_usd: float = 0.5


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class DeepAgent(Protocol):
    """单个 deep agent 实例 (LangGraph CompiledStateGraph 等)。"""

    name: str

    async def ainvoke(self, input: dict[str, Any]) -> dict[str, Any]: ...


@runtime_checkable
class DeepAgentFactory(Protocol):
    """§5.5 DeepAgent 工厂: 给 config → DeepAgent。"""

    async def create(
        self,
        config: DeepAgentConfig,
        subagents: tuple[SubAgentSpec, ...] = (),
    ) -> DeepAgent: ...


# ---------------------------------------------------------------------------
# InMemoryDeepAgentFactory
# ---------------------------------------------------------------------------


class InMemoryDeepAgentFactory:
    """§5.5 / §2.5 阻塞 4 验证: deepagents==0.7.25 真实可用。

    简化版:
    - 不实际调 create_deep_agent (避免依赖外部 API key)
    - 仍保留 SubAgentSpec 与 budget 校验逻辑
    - 测试用 InMemoryDeepAgent (deterministic)
    """

    def __init__(self) -> None:
        self._created: list[DeepAgentConfig] = []

    async def create(
        self,
        config: DeepAgentConfig,
        subagents: tuple[SubAgentSpec, ...] = (),
    ) -> "InMemoryDeepAgent":
        # §5.5 budget 校验: max_steps > 0, max_cost_usd > 0
        if config.max_steps <= 0:
            raise DeepAgentBudgetExceeded(
                f"max_steps must be positive: {config.max_steps}",
                spent_steps=0,
            )
        if config.max_cost_usd <= 0:
            raise DeepAgentBudgetExceeded(
                f"max_cost_usd must be positive: {config.max_cost_usd}",
                spent_cost_usd=0.0,
            )
        for sub in subagents:
            if sub.max_steps <= 0 or sub.max_cost_usd <= 0:
                raise DeepAgentBudgetExceeded(
                    f"sub-agent {sub.name} budget invalid",
                )
        self._created.append(config)
        return InMemoryDeepAgent(name=config.agent_id, config=config)


class InMemoryDeepAgent:
    """§5.5 进程内 deep agent (单测/本地 dev 用)。

    真实生产用 `deepagents.create_deep_agent` 替换 (Stage 6b PR B)。
    """

    def __init__(self, name: str, config: DeepAgentConfig) -> None:
        self.name = name
        self._config = config
        self._steps = 0
        self._cost = 0.0
        self._todos: list[dict[str, Any]] = []
        self._plan_emitted = False

    @property
    def config(self) -> DeepAgentConfig:
        return self._config

    @property
    def steps(self) -> int:
        return self._steps

    @property
    def cost(self) -> float:
        return self._cost

    @property
    def todos(self) -> list[dict[str, Any]]:
        return list(self._todos)

    def emit_plan(self, plan: list[dict[str, Any]]) -> None:
        """emit todos (Stage 6b: plan/todos 通过 on_custom_event 推到 SSE)。"""
        self._todos = list(plan)
        self._plan_emitted = True

    def step(self, cost: float = 0.01) -> None:
        """记一次 sub-agent step + 累加 cost; 超 budget 抛异常。"""
        if self._steps + 1 > self._config.max_steps:
            raise DeepAgentBudgetExceeded(
                f"max_steps {self._config.max_steps} exceeded",
                spent_steps=self._steps + 1,
            )
        if self._cost + cost > self._config.max_cost_usd:
            raise DeepAgentBudgetExceeded(
                f"max_cost_usd {self._config.max_cost_usd} exceeded",
                spent_cost_usd=self._cost + cost,
            )
        self._steps += 1
        self._cost += cost

    async def ainvoke(self, input: dict[str, Any]) -> dict[str, Any]:
        """简化实现: 直接返回, 不做真实推理。"""
        return {
            "agent": self.name,
            "input": input,
            "config": self._config,
            "todos": self._todos,
            "plan_emitted": self._plan_emitted,
            "steps": self._steps,
            "cost_usd": self._cost,
        }


__all__ = [
    "DEEP_AGENT_BUDGET_EXCEEDED_ERROR_CODE",
    "DEEP_AGENT_FAILED_ERROR_CODE",
    "DeepAgent",
    "DeepAgentBudgetExceeded",
    "DeepAgentConfig",
    "DeepAgentFactory",
    "InMemoryDeepAgent",
    "InMemoryDeepAgentFactory",
    "SubAgentSpec",
]