"""Smoke tests for observability (no I/O)."""

from __future__ import annotations

from qzdap_observability.logging import configure_logging, get_logger
from qzdap_observability.metrics import (
    HTTP_REQUESTS_TOTAL,
    LEGACY_CALL_LAST_TIMESTAMP,
    LEGACY_CALLS_TOTAL,
    record_http_request,
    record_legacy_call,
    record_router_concurrency_rejected,
    record_router_queue_depth,
    record_router_queue_wait,
    record_router_session_key_hash,
    render_prometheus,
)
from qzdap_observability.tracing import configure_tracing, get_tracer


def test_configure_logging_does_not_raise() -> None:
    configure_logging(level="INFO", json=False)
    log = get_logger("test")
    log.info("hello", foo="bar")


def test_record_http_request_increments() -> None:
    before = HTTP_REQUESTS_TOTAL.labels(method="GET", route="/x", status="200")._value.get()
    record_http_request("GET", "/x", 200, 0.123)
    after = HTTP_REQUESTS_TOTAL.labels(method="GET", route="/x", status="200")._value.get()
    assert after > before


def test_render_prometheus_returns_bytes() -> None:
    body, content_type = render_prometheus()
    assert isinstance(body, bytes)
    assert b"qzdap_http_requests_total" in body
    assert content_type.startswith("text/plain")


def test_record_legacy_call_counts_per_entry() -> None:
    """旧实现调用计数 —— 收敛判据（≥7 天 + 占比 ≥95% + 本指标归零）依赖它。"""
    before = LEGACY_CALLS_TOTAL.labels(entry="G1")._value.get()
    record_legacy_call("G1")
    record_legacy_call("G1")
    after = LEGACY_CALLS_TOTAL.labels(entry="G1")._value.get()
    assert after == before + 2

    other = LEGACY_CALLS_TOTAL.labels(entry="G2")._value.get()
    assert other == 0


def test_record_legacy_call_updates_last_timestamp() -> None:
    before = LEGACY_CALL_LAST_TIMESTAMP.labels(entry="X11")._value.get()
    record_legacy_call("X11")
    after = LEGACY_CALL_LAST_TIMESTAMP.labels(entry="X11")._value.get()
    assert after >= before


def test_legacy_metric_is_exposed() -> None:
    record_legacy_call("R3")
    body, _ = render_prometheus()
    assert b'qzdap_legacy_calls_total{entry="R3"}' in body


def test_the_router_queue_metrics_are_exposed() -> None:
    """**Router 的排队指标** ✓（Router 方案 §12.2 ✓）。"""
    record_router_queue_depth(tenant_id="t1", depth=3)
    record_router_queue_wait(tenant_id="t1", waited_s=0.5)
    record_router_concurrency_rejected(reason="queue_full")
    record_router_session_key_hash()
    body, _ = render_prometheus()
    assert b'qzdap_router_queue_depth{tenant_id="t1"}' in body
    assert b'qzdap_router_queue_wait_seconds_count{tenant_id="t1"}' in body
    assert b'qzdap_router_concurrency_rejected_total{reason="queue_full"}' in body
    assert b"qzdap_router_session_key_hash_total" in body


def test_configure_tracing_is_idempotent() -> None:
    configure_tracing()
    configure_tracing()  # must not raise
    tracer = get_tracer("test")
    assert tracer is not None
