"""Observability — UsageTracker + CostAttribution + DegradedCounter (§5.10 / §8 Stage 7a)。

Stage 7a PR A 范围：

- `UsageTracker` 跨 19 节点累加 token / cost, done 节点汇总 emit
- `CostAttribution` 按 (tenant, workspace, user, agent) 维度累加
- `DegradedCounter` 计数 observability 失败 (§5.10 决议: 不静默吞)
- Prometheus-style counter（in-memory 进程内, 生产接 /metrics 端点）

§5.10 UsageChunk 必带 6 维度:
- tenant_id / workspace_id / user_id / agent_id / agent_version / model_version

§8 Stage 7a 退出条件:
- UsageChunk 携带完整维度
- degraded 计数递增告警
- observability 失败不静默吞掉
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol, runtime_checkable


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Degraded counter (§5.10 4 类)
# ---------------------------------------------------------------------------


class DegradedKind(str, Enum):
    """§5.10 4 类降级标志。"""

    RECALL = "recall"
    COMPACTION = "compaction"
    LANGSMITH = "langsmith"
    COST_ATTRIBUTION = "cost_attribution"


@dataclass
class DegradedCounter:
    """§5.10 + §8 Stage 7a: 4 类降级计数器。

    生产实现暴露为 Prometheus counter:
        qzdap_observability_degraded_total{degraded=recall|compaction|langsmith|cost_attribution}
    """

    _counts: dict[str, int] = field(default_factory=lambda: defaultdict(int))

    def inc(self, kind: DegradedKind, n: int = 1) -> None:
        self._counts[kind.value] += n
        # §5.10: observability 失败不静默吞, 必须有计数和 warning
        logger.warning(
            "observability degraded: kind=%s count=%s total=%s",
            kind.value, n, self._counts[kind.value],
        )

    def value(self, kind: DegradedKind) -> int:
        return self._counts[kind.value]

    def snapshot(self) -> dict[str, int]:
        """返回所有 4 类的当前计数, 缺失的补 0。"""
        return {kind.value: self._counts[kind.value] for kind in DegradedKind}

    def export_prometheus(self) -> str:
        """§8 Stage 7a: Prometheus counter 格式输出。"""
        lines = [
            "# HELP qzdap_observability_degraded_total Count of observability degraded events",
            "# TYPE qzdap_observability_degraded_total counter",
        ]
        for kind in DegradedKind:
            value = self._counts[kind.value]
            lines.append(
                f'qzdap_observability_degraded_total{{degraded="{kind.value}"}} {value}'
            )
        return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# UsageTracker (§5.10)
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class UsageRecord:
    """§5.10 跨 19 节点累加的 usage 记录。"""

    tenant_id: str
    workspace_id: str
    user_id: str
    agent_id: str
    agent_version: str
    model_version: str

    input_tokens: int = 0
    output_tokens: int = 0
    cache_tokens: int = 0
    cost_usd: float | None = None
    cost_unknown: bool = True
    retry_count: int = 0

    def to_usage_event_dict(self) -> dict[str, Any]:
        """§5.10 emit 前的 dict 形式 (用于 done 节点 emit)。"""
        return {
            "kind": "usage",
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_tokens": self.cache_tokens,
            "cost_usd": self.cost_usd,
            "cost_unknown": self.cost_unknown,
            "tenant_id": self.tenant_id,
            "workspace_id": self.workspace_id,
            "user_id": self.user_id,
            "agent_id": self.agent_id,
            "agent_version": self.agent_version,
            "model_version": self.model_version,
            "retry_count": self.retry_count,
        }


class UsageTracker:
    """§5.10 UsageTracker — 跨 19 节点累加 token / cost, done 节点汇总 emit。"""

    def __init__(self) -> None:
        self._records: dict[str, UsageRecord] = {}  # turn_id -> UsageRecord
        self._degraded = DegradedCounter()

    @property
    def degraded(self) -> DegradedCounter:
        return self._degraded

    def start(self, turn_id: str, *, tenant_id: str, workspace_id: str,
              user_id: str, agent_id: str, agent_version: str, model_version: str) -> None:
        """turn 开始时初始化 UsageRecord。"""
        self._records[turn_id] = UsageRecord(
            tenant_id=tenant_id, workspace_id=workspace_id, user_id=user_id,
            agent_id=agent_id, agent_version=agent_version,
            model_version=model_version,
        )

    def add_tokens(self, turn_id: str, *,
                   input_tokens: int = 0, output_tokens: int = 0,
                   cache_tokens: int = 0) -> None:
        """累加 token (任何节点都可以调)。"""
        rec = self._records.get(turn_id)
        if rec is None:
            return  # 静默忽略: turn 未初始化 (Stage 1 fake 兼容)
        rec.input_tokens += input_tokens
        rec.output_tokens += output_tokens
        rec.cache_tokens += cache_tokens

    def set_cost(self, turn_id: str, cost_usd: float, *, retry_count: int = 0) -> None:
        """设置 cost (模型回调完成后)。"""
        rec = self._records.get(turn_id)
        if rec is None:
            return
        rec.cost_usd = cost_usd
        rec.cost_unknown = False
        rec.retry_count = retry_count

    def mark_cost_unknown(self, turn_id: str) -> None:
        """cost 未知 (模型无价格表), §5.10 必须显式标记 + cost_attribution_degraded。"""
        rec = self._records.get(turn_id)
        if rec is None:
            return
        rec.cost_unknown = True
        self._degraded.inc(DegradedKind.COST_ATTRIBUTION)

    def get(self, turn_id: str) -> UsageRecord | None:
        return self._records.get(turn_id)

    def discard(self, turn_id: str) -> None:
        self._records.pop(turn_id, None)

    def all_turns(self) -> list[str]:
        return list(self._records.keys())


# ---------------------------------------------------------------------------
# CostAttribution (§5.10 / §8 Stage 7a)
# ---------------------------------------------------------------------------


@runtime_checkable
class CostAttribution(Protocol):
    """§5.10 成本归属: 按 tenant/workspace/user/agent 维度累加。"""

    def record(self, usage: UsageRecord) -> None: ...

    def by_tenant(self, tenant_id: str) -> float: ...


class InMemoryCostAttribution:
    """§5.10 进程内成本归属, 接 /metrics 端点或 sync 到 cost_attribution 表。"""

    def __init__(self) -> None:
        # key: (tenant_id, workspace_id, user_id, agent_id) -> cost
        self._costs: dict[tuple[str, str, str, str], float] = defaultdict(float)
        self._calls: dict[tuple[str, str, str, str], int] = defaultdict(int)

    def record(self, usage: UsageRecord) -> None:
        if usage.cost_usd is None or usage.cost_unknown:
            return  # 跳过未知 cost
        key = (usage.tenant_id, usage.workspace_id, usage.user_id, usage.agent_id)
        self._costs[key] += usage.cost_usd
        self._calls[key] += 1

    def by_tenant(self, tenant_id: str) -> float:
        return sum(v for k, v in self._costs.items() if k[0] == tenant_id)

    def snapshot(self) -> dict[tuple[str, str, str, str], dict[str, float]]:
        out: dict[tuple[str, str, str, str], dict[str, float]] = {}
        for k, cost in self._costs.items():
            out[k] = {"cost_usd": cost, "calls": self._calls[k]}
        return out


__all__ = [
    "CostAttribution",
    "DegradedCounter",
    "DegradedKind",
    "InMemoryCostAttribution",
    "UsageRecord",
    "UsageTracker",
]