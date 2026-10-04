"""Prometheus metrics.

A thin wrapper over `prometheus_client` with a single default registry that
the HTTP layer exposes at `/metrics`. We intentionally do NOT expose a global
`REGISTRY`; tests can spin up their own.
"""

from __future__ import annotations

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


def record_http_request(
    method: str, route: str, status: int, duration_s: float
) -> None:
    HTTP_REQUESTS_TOTAL.labels(method=method, route=route, status=str(status)).inc()
    HTTP_REQUEST_DURATION.labels(
        method=method, route=route, status=str(status)
    ).observe(duration_s)


def render_prometheus() -> tuple[bytes, str]:
    return generate_latest(metrics_registry), CONTENT_TYPE_LATEST


# Re-export for callers that want to define their own
MetricsRegistry = CollectorRegistry
