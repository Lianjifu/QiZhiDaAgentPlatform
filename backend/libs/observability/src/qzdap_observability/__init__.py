"""Observability: logging, tracing, Prometheus metrics."""

from qzdap_observability.logging import configure_logging, get_logger
from qzdap_observability.metrics import (
    LEGACY_CALL_LAST_TIMESTAMP,
    LEGACY_CALLS_TOTAL,
    Counter,
    Gauge,
    Histogram,
    MetricsRegistry,
    metrics_registry,
    record_http_request,
    record_legacy_call,
    render_prometheus,
)
from qzdap_observability.middleware import ObservabilityMiddleware
from qzdap_observability.tracing import (
    configure_tracing,
    current_span,
    get_tracer,
    shutdown_tracing,
)

__all__ = [
    "LEGACY_CALLS_TOTAL",
    "LEGACY_CALL_LAST_TIMESTAMP",
    "Counter",
    "Gauge",
    "Histogram",
    "MetricsRegistry",
    "ObservabilityMiddleware",
    "configure_logging",
    "configure_tracing",
    "current_span",
    "get_logger",
    "get_tracer",
    "metrics_registry",
    "record_http_request",
    "record_legacy_call",
    "render_prometheus",
    "shutdown_tracing",
]
