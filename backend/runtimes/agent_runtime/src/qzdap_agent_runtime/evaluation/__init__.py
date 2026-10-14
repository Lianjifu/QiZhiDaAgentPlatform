"""Online evaluation + rollout (engine v0/v1) — §8 Stage 7b。

Stage 7b PR A 范围：

- `EvalMetric` dataclass: recall_at_k / mrr / ndcg / groundedness / citation_coverage
- `EvalRecord`: turn_id + 5 指标 + timestamp
- `OnlineEvaluator` Protocol: async 评估 (不阻塞主路径)
- `InMemoryOnlineEvaluator`:
  - 不阻塞: 走 background task / 队列
  - 收集 5 指标
  - 按 turn_id 查询
- `RolloutPolicy`: 决定某 (agent_id, tenant_id) 用 v0 还是 v1
- `EngineSwitch`:
  - `pick_engine_version(agent_id, tenant_id)` -> "v0" | "v1"
  - 灰度比例 + 强制 v0/v1 列表
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


# ---------------------------------------------------------------------------
# Eval metrics
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class EvalMetric:
    """§8 Stage 7b: 5 个评测指标。"""

    recall_at_k: float = 0.0       # @ k=5
    mrr: float = 0.0              # Mean Reciprocal Rank
    ndcg: float = 0.0             # Normalized Discounted Cumulative Gain
    groundedness: float = 0.0     # 答案是否基于召回 (0-1)
    citation_coverage: float = 0.0  # 召回被引用的比例 (0-1)

    def to_dict(self) -> dict[str, float]:
        return {
            "recall_at_k": self.recall_at_k,
            "mrr": self.mrr,
            "ndcg": self.ndcg,
            "groundedness": self.groundedness,
            "citation_coverage": self.citation_coverage,
        }


@dataclass
class EvalRecord:
    """§8 Stage 7b: 单条 turn 的评测记录。"""

    turn_id: str
    agent_id: str
    tenant_id: str
    metrics: EvalMetric
    engine_version: str  # "v0" | "v1"
    occurred_at: float = field(default_factory=time.time)
    eval_id: str = field(default_factory=lambda: str(uuid.uuid4()))


# ---------------------------------------------------------------------------
# OnlineEvaluator Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class OnlineEvaluator(Protocol):
    """§8 Stage 7b: 异步评测 (不阻塞主路径)。"""

    async def evaluate(
        self,
        *,
        turn_id: str,
        agent_id: str,
        tenant_id: str,
        engine_version: str,
        query: str,
        answer: str,
        retrieved_context: list[dict[str, Any]],
        gold_evidence: list[dict[str, Any]] | None = None,
    ) -> EvalMetric: ...


# ---------------------------------------------------------------------------
# InMemoryOnlineEvaluator
# ---------------------------------------------------------------------------


class InMemoryOnlineEvaluator:
    """§8 Stage 7b: 进程内异步评测 (不阻塞主路径)。

    实现:
    - evaluate() 用 asyncio.create_task() 后台跑
    - 主路径不 await, 立即返回空 metrics
    - 完成后 metrics 写入 self._records[turn_id]
    """

    def __init__(self) -> None:
        self._records: dict[str, EvalRecord] = {}
        # 已 gold 证据的 fixture (测试用)
        self._gold_evidence: dict[str, list[dict[str, Any]]] = {}

    @property
    def records(self) -> list[EvalRecord]:
        return list(self._records.values())

    def get(self, turn_id: str) -> EvalRecord | None:
        return self._records.get(turn_id)

    async def evaluate(
        self,
        *,
        turn_id: str,
        agent_id: str,
        tenant_id: str,
        engine_version: str,
        query: str,
        answer: str,
        retrieved_context: list[dict[str, Any]],
        gold_evidence: list[dict[str, Any]] | None = None,
    ) -> EvalMetric:
        """§8 Stage 7b: 异步评测, 不阻塞主路径。

        真实生产用专门 eval worker (Kafka consumer / cron);
        这里用 asyncio.create_task() 模拟。
        """
        coro = self._evaluate_async(
            turn_id=turn_id, agent_id=agent_id, tenant_id=tenant_id,
            engine_version=engine_version, query=query, answer=answer,
            retrieved_context=retrieved_context, gold_evidence=gold_evidence,
        )
        # 尝试在当前 event loop 调度; 同步上下文则保留为 pending coroutine
        try:
            loop = asyncio.get_running_loop()
            task = loop.create_task(coro)
            if not hasattr(self, "_pending_tasks"):
                self._pending_tasks = []
            self._pending_tasks.append(task)
        except RuntimeError:
            # 同步上下文: 保存 coroutine, 等待 wait_pending() 时执行
            if not hasattr(self, "_pending_coros"):
                self._pending_coros = []
            self._pending_coros.append(coro)
        return EvalMetric()  # 占位: 真实值由后台任务写

    async def _evaluate_async(
        self,
        *,
        turn_id: str,
        agent_id: str,
        tenant_id: str,
        engine_version: str,
        query: str,
        answer: str,
        retrieved_context: list[dict[str, Any]],
        gold_evidence: list[dict[str, Any]] | None = None,
    ) -> None:
        """真实计算 5 个指标 (后台任务)。"""
        gold = gold_evidence or self._gold_evidence.get(turn_id, [])
        # 简化: 基于 retrieved vs gold 算指标
        if not gold:
            metrics = EvalMetric(
                recall_at_k=0.0, mrr=0.0, ndcg=0.0,
                groundedness=1.0 if answer else 0.0,
                citation_coverage=0.0,
            )
        else:
            gold_ids = {g.get("source_id") or g.get("id") for g in gold}
            retrieved_ids = [c.get("source_id") for c in retrieved_context]
            # Recall@k
            hits = sum(1 for gid in gold_ids if gid and gid in retrieved_ids)
            recall_at_k = hits / len(gold_ids) if gold_ids else 0.0
            # MRR
            mrr = 0.0
            for i, rid in enumerate(retrieved_ids, 1):
                if rid in gold_ids:
                    mrr = 1.0 / i
                    break
            # nDCG (简化: binary relevance)
            import math
            dcg = sum(
                1.0 / math.log2(i + 1) for i, rid in enumerate(retrieved_ids, 1)
                if rid in gold_ids
            )
            idcg = sum(1.0 / math.log2(i + 1) for i in range(1, min(len(gold), len(retrieved_ids)) + 1))
            ndcg = dcg / idcg if idcg > 0 else 0.0
            # groundedness: 答案非空 + 召回了相关 + 至少 1 个 gold
            groundedness = 1.0 if (answer and hits > 0) else 0.0
            # citation_coverage: 召回中 gold 占比
            citation_coverage = hits / len(retrieved_ids) if retrieved_ids else 0.0
            metrics = EvalMetric(
                recall_at_k=recall_at_k,
                mrr=mrr,
                ndcg=ndcg,
                groundedness=groundedness,
                citation_coverage=citation_coverage,
            )
        self._records[turn_id] = EvalRecord(
            turn_id=turn_id, agent_id=agent_id, tenant_id=tenant_id,
            metrics=metrics, engine_version=engine_version,
        )

    def set_gold_evidence(self, turn_id: str, evidence: list[dict[str, Any]]) -> None:
        """测试用: 注入 gold 证据。"""
        self._gold_evidence[turn_id] = list(evidence)

    async def wait_pending(self) -> None:
        """测试辅助: 等待所有 pending 任务完成。

        同时处理:
        - 已通过 create_task() 调度的 task (在 _pending_tasks)
        - 在同步上下文保存的 coroutine (在 _pending_coros, 需在 event loop 中 run)
        """
        tasks = getattr(self, "_pending_tasks", [])
        coros = getattr(self, "_pending_coros", [])
        all_tasks = list(tasks)
        # 在当前 loop 跑 coros
        if coros:
            for c in coros:
                all_tasks.append(asyncio.create_task(c))
        if all_tasks:
            await asyncio.gather(*all_tasks, return_exceptions=True)
            self._pending_tasks = []
            self._pending_coros = []


# ---------------------------------------------------------------------------
# EngineSwitch + RolloutPolicy
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RolloutPolicy:
    """§8 Stage 7b: 灰度策略 (按 (agent_id, tenant_id) 决定 v0/v1)。"""

    rollout_percent: int = 0  # 0-100, 多少比例的请求走 v1
    force_v1_agents: frozenset[str] = field(default_factory=frozenset)
    force_v0_agents: frozenset[str] = field(default_factory=frozenset)
    force_v1_tenants: frozenset[str] = field(default_factory=frozenset)
    force_v0_tenants: frozenset[str] = field(default_factory=frozenset)
    salt: str = "qzdap-rollout"


def _stable_bucket(agent_id: str, tenant_id: str, salt: str) -> int:
    """§8 Stage 7b: 稳定分桶 (0-99) — 同一 agent/tenant 永远落入同一 bucket。

    用 SHA-256 的 4 字节 (32-bit) mod 100, 比单字节分布更均匀。
    """
    import hashlib
    key = f"{salt}:{agent_id}:{tenant_id}".encode("utf-8")
    h = hashlib.sha256(key).digest()
    val = int.from_bytes(h[:4], "big", signed=False)
    return val % 100


@dataclass(frozen=True, slots=True)
class EngineSwitch:
    """§8 Stage 7b: 灰度开关 (按 RolloutPolicy 决定 v0/v1)。"""

    policy: RolloutPolicy

    def pick_engine_version(self, *, agent_id: str, tenant_id: str) -> str:
        """§8 Stage 7b 退出条件: 灰度回退即时生效。

        优先级: 强制列表 > rollout_percent。
        """
        if agent_id in self.policy.force_v0_agents or tenant_id in self.policy.force_v0_tenants:
            return "v0"
        if agent_id in self.policy.force_v1_agents or tenant_id in self.policy.force_v1_tenants:
            return "v1"
        bucket = _stable_bucket(agent_id, tenant_id, self.policy.salt)
        if bucket < self.policy.rollout_percent:
            return "v1"
        return "v0"


__all__ = [
    "EngineSwitch",
    "EvalMetric",
    "EvalRecord",
    "InMemoryOnlineEvaluator",
    "OnlineEvaluator",
    "RolloutPolicy",
]