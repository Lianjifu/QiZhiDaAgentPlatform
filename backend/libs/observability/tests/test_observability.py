"""Smoke tests for observability (no I/O)."""

from __future__ import annotations

from qzdap_observability.logging import configure_logging, get_logger
from qzdap_observability.metrics import (
    HTTP_REQUESTS_TOTAL,
    record_http_request,
    render_prometheus,
)
from qzdap_observability.tracing import configure_tracing, get_tracer


def test_configure_logging_does_not_raise() -> None:
    configure_logging(level="INFO", json=False)
    log = get_logger("test")
    log.info("hello", foo="bar")


def test_record_http_request_increments() -> None:
    before = HTTP_REQUESTS_TOTAL.labels(
        method="GET", route="/x", status="200"
    )._value.get()
    record_http_request("GET", "/x", 200, 0.123)
    after = HTTP_REQUESTS_TOTAL.labels(
        method="GET", route="/x", status="200"
    )._value.get()
    assert after > before


def test_render_prometheus_returns_bytes() -> None:
    body, content_type = render_prometheus()
    assert isinstance(body, bytes)
    assert b"qzdap_http_requests_total" in body
    assert content_type.startswith("text/plain")


def test_configure_tracing_is_idempotent() -> None:
    configure_tracing()
    configure_tracing()  # must not raise
    tracer = get_tracer("test")
    assert tracer is not None
