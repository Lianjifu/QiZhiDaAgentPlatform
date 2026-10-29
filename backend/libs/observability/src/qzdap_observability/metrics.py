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


def render_prometheus() -> tuple[bytes, str]:
    return generate_latest(metrics_registry), CONTENT_TYPE_LATEST


# Re-export for callers that want to define their own
MetricsRegistry = CollectorRegistry
