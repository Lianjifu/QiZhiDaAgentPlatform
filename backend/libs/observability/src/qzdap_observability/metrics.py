"""Prometheus metrics.

A thin wrapper over `prometheus_client` with a single default registry that
the HTTP layer exposes at `/metrics`. We intentionally do NOT expose a global
`REGISTRY`; tests can spin up their own.
"""

from __future__ import annotations

import time

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

metrics_registry = CollectorRegistry()

# Pre-defined common metrics
HTTP_REQUESTS_TOTAL = Counter(
    "qzdap_http_requests_total",
    "Total HTTP requests",
    labelnames=("method", "route", "status"),
    registry=metrics_registry,
)
HTTP_REQUEST_DURATION = Histogram(
    "qzdap_http_request_duration_seconds",
    "HTTP request duration in seconds",
    labelnames=("method", "route", "status"),
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
    registry=metrics_registry,
)
SSE_FIRST_CHUNK_LATENCY = Histogram(
    "qzdap_sse_first_chunk_seconds",
    "Latency from request start to first SSE chunk",
    labelnames=("agent_id",),
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 5),
    registry=metrics_registry,
)
LLM_TOKENS_TOTAL = Counter(
    "qzdap_llm_tokens_total",
    "LLM tokens used",
    labelnames=("provider", "model", "direction"),
    registry=metrics_registry,
)
LLM_COST_USD = Counter(
    "qzdap_llm_cost_usd_total",
    "Cumulative LLM cost in USD",
    labelnames=("provider", "model"),
    registry=metrics_registry,
)
ACTIVE_TURNS = Gauge(
    "qzdap_active_turns",
    "Turns currently in-flight",
    registry=metrics_registry,
)
# 旧实现调用计数 —— 收敛判据的唯一依据。
# 标签 `entry` 取自 cleanup-ledger 的台账编号（G1 / R3 / X11 …）。
# 清理窗口内该指标必须归零，否则对应旧实现不许删除。
LEGACY_CALLS_TOTAL = Counter(
    "qzdap_legacy_calls_total",
    "Calls to legacy (deprecated) implementations, by cleanup-ledger entry id",
    labelnames=("entry",),
    registry=metrics_registry,
)
LEGACY_CALL_LAST_TIMESTAMP = Gauge(
    "qzdap_legacy_call_last_timestamp_seconds",
    "Unix timestamp of the most recent call to a legacy implementation",
    labelnames=("entry",),
    registry=metrics_registry,
)
# 新实现调用计数 —— 与 LEGACY_CALLS_TOTAL 同源同标签，供
# 「新路径流量占比 ≥95%」的删除判据使用（README §3.1 的删除条件客观化）。
NEW_CALLS_TOTAL = Counter(
    "qzdap_new_calls_total",
    "Calls to replacement implementations, by cleanup-ledger entry id",
    labelnames=("entry",),
    registry=metrics_registry,
)
# 路由决策计数 —— 标签 `strategy` 是命中的规则（sticky / explicit /
# business_line / user_tag / fallback），`outcome` 是结果
# （matched / fallback / rejected）。
# 「兜底命中率」= outcome="fallback" 的占比 —— 突增说明策略覆盖不足
# （router-refactor-plan §12.2）。
ROUTER_ROUTE_TOTAL = Counter(
    "qzdap_router_route_total",
    "Routing decisions by the rule that matched",
    labelnames=("strategy", "outcome"),
    registry=metrics_registry,
)
# 单次路由决策的耗时。
ROUTER_ROUTE_DURATION = Histogram(
    "qzdap_router_route_duration_seconds",
    "Routing decision latency in seconds",
    labelnames=("strategy",),
    registry=metrics_registry,
)
# ⚠️ **入站序号快照漂移** ✓（Router 方案 §4.2 ✓）—— 兜底放行路径的命中
# 次数 ✓。**正常应恒为 0** ✓ —— 持续 > 0 说明有系统性问题 ✓
# （轮次终态与会话快照的更新不在同一个事务里 ✓）。
ROUTER_SEQ_SNAPSHOT_DRIFT_TOTAL = Counter(
    "qzdap_router_seq_snapshot_drift_total",
    "FIFO fallback releases caused by a stale last_completed_seq snapshot",
    registry=metrics_registry,
)
# ⚠️ **当前排队深度** ✓（Router 方案 §12.2 ✓）—— 只在排队开关打开时上报 ✓
# （标签是租户 ✓ —— 不打会话 key ✓ —— key 是哈希的 ✓）。
ROUTER_QUEUE_DEPTH = Gauge(
    "qzdap_router_queue_depth",
    "Turns currently waiting for their FIFO slot",
    labelnames=("tenant_id",),
    registry=metrics_registry,
)
# ⚠️ **排队等待时长** ✓（Router 方案 §12.2 ✓）。
ROUTER_QUEUE_WAIT = Histogram(
    "qzdap_router_queue_wait_seconds",
    "Time a turn waited for its FIFO slot",
    labelnames=("tenant_id",),
    registry=metrics_registry,
)
# ⚠️ **因并发上限被拒** ✓（Router 方案 §12.2 ✓）—— 排队语义下「被拒」=
# **队列满 / 等超时** ✓（`reason`：``queue_full`` / ``queue_timeout`` ✓）。
ROUTER_CONCURRENCY_REJECTED_TOTAL = Counter(
    "qzdap_router_concurrency_rejected_total",
    "Turns refused by the per-session concurrency limit",
    labelnames=("reason",),
    registry=metrics_registry,
)
# ⚠️ **向量补写** ✓（Memory 方案 §5.4 ✓）—— 标签是结果 ✓（``enqueued`` ✓ /
# ``dropped`` ✓ —— **队列满了被丢** ✓ —— 丢了要看得见 ✓）。
MEMORY_VECTOR_ENQUEUED_TOTAL = Counter(
    "qzdap_memory_vector_enqueued_total",
    "Vector write jobs accepted (or dropped when the queue is full)",
    labelnames=("outcome",),
    registry=metrics_registry,
)
# ⚠️ **淘汰计数** ✓（Memory 方案 §14.2 ✓）—— 标签是**原因** ✓
# （``ttl`` / ``max_items`` / ``storage`` ✓）。
MEMORY_EVICTION_TOTAL = Counter(
    "qzdap_memory_eviction_total",
    "Memories retired by the retention policy",
    labelnames=("reason",),
    registry=metrics_registry,
)
# ⚠️ **会话 key 派生次数** ✓（Router 方案 §12.2 ✓）—— **不记录 key 本身** ✓
# （避免泄漏身份 ✓ —— key 会进日志 / 审计 / 数据库 ✓）。
ROUTER_SESSION_KEY_HASH_TOTAL = Counter(
    "qzdap_router_session_key_hash_total",
    "Session keys derived from external identities",
    registry=metrics_registry,
)


def record_http_request(
    method: str, route: str, status: int, duration_s: float
) -> None:
    HTTP_REQUESTS_TOTAL.labels(method=method, route=route, status=str(status)).inc()
    HTTP_REQUEST_DURATION.labels(
        method=method, route=route, status=str(status)
    ).observe(duration_s)


def record_legacy_call(entry: str) -> None:
    """记录一次旧实现调用。

    ``entry`` 是 cleanup-ledger 的台账编号（如 ``"G1"``）。旧实现被新路径接管时
    打这个点，清理判据（连续 ≥7 天 + 新路径占比 ≥95% + 本指标归零）依赖它。
    """
    LEGACY_CALLS_TOTAL.labels(entry=entry).inc()
    LEGACY_CALL_LAST_TIMESTAMP.labels(entry=entry).set(time.time())


def record_new_call(entry: str) -> None:
    """记录一次新实现调用（与 :func:`record_legacy_call` 同一套 ``entry`` 标签）。"""
    NEW_CALLS_TOTAL.labels(entry=entry).inc()


def record_router_route(*, strategy: str, outcome: str, duration_s: float = 0.0) -> None:
    """记录一次路由决策 —— ``strategy`` 是命中的规则，``outcome`` 是结果。

    用于回答「为什么是这个 agent」的**聚合**视角：兜底占比突增说明策略覆盖
    不足，显式占比高说明策略还没被用起来（router-refactor-plan §12.2）。
    """
    ROUTER_ROUTE_TOTAL.labels(strategy=strategy, outcome=outcome).inc()
    if duration_s:
        ROUTER_ROUTE_DURATION.labels(strategy=strategy).observe(duration_s)


def record_router_seq_snapshot_drift() -> None:
    """**记一次快照漂移** ✓（Router 方案 §4.2 的兜底路径命中 ✓）。

    ⚠️ **正常应恒为 0** ✓ —— 持续 > 0 说明轮次终态与会话快照的更新**没在
    同一个事务里** ✓（系统性问题 ✓）。
    """
    ROUTER_SEQ_SNAPSHOT_DRIFT_TOTAL.inc()


def record_router_queue_depth(*, tenant_id: str, depth: int) -> None:
    """**上报当前排队深度** ✓（Router 方案 §12.2 ✓）。"""
    ROUTER_QUEUE_DEPTH.labels(tenant_id=str(tenant_id)).set(int(depth))


def record_router_queue_wait(*, tenant_id: str, waited_s: float) -> None:
    """**上报排队等待时长** ✓（Router 方案 §12.2 ✓）。"""
    ROUTER_QUEUE_WAIT.labels(tenant_id=str(tenant_id)).observe(float(waited_s))


def record_router_concurrency_rejected(*, reason: str) -> None:
    """**记一次被拒** ✓（队列满 / 等超时 ✓ —— Router 方案 §12.2 ✓）。

    ⚠️ **排队语义下也有「被拒」** ✓ —— 决策 #7：超限**不静默丢弃** ✓，
    而是把这一轮落成终态并报上来 ✓。
    """
    ROUTER_CONCURRENCY_REJECTED_TOTAL.labels(reason=str(reason)).inc()


def record_memory_vector_enqueue(*, dropped: bool = False) -> None:
    """**记一次向量补写排队** ✓（Memory 方案 §5.4 ✓）。

    ⚠️ **队列满了被丢** ✓ —— 那是**要看得见**的事件 ✓（补写兜底会捡回来 ✓，
    但一直丢说明队列不够用 ✗✗）。
    """
    MEMORY_VECTOR_ENQUEUED_TOTAL.labels(
        outcome="dropped" if dropped else "enqueued"
    ).inc()


def record_memory_eviction(*, reason: str, count: int = 1) -> None:
    """**记一次淘汰** ✓（Memory 方案 §14.2 ✓ —— ``qzdap_memory_eviction_total`` ✓）。

    ⚠️ **按原因分开** ✓（TTL / 条数 / 容量 ✓）—— 才知道是哪条规则在起作用 ✓。
    """
    if count <= 0:
        return
    MEMORY_EVICTION_TOTAL.labels(reason=str(reason)).inc(count)


def record_router_session_key_hash() -> None:
    """**记一次会话 key 派生** ✓（Router 方案 §12.2 ✓ —— 不记录 key 本身 ✓）。"""
    ROUTER_SESSION_KEY_HASH_TOTAL.inc()


def render_prometheus() -> tuple[bytes, str]:
    return generate_latest(metrics_registry), CONTENT_TYPE_LATEST


# Re-export for callers that want to define their own
MetricsRegistry = CollectorRegistry
