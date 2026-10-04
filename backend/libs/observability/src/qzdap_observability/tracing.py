"""OpenTelemetry tracing bootstrap."""

from __future__ import annotations

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import TraceIdRatioBased

# The OTLP gRPC exporter (opentelemetry-exporter-otlp-proto-grpc) is an
# optional runtime dependency; we import it lazily inside `configure_tracing`
# only when an OTLP endpoint is configured. Tests + dev do not require it.

_PROVIDER: TracerProvider | None = None


def configure_tracing(
    *,
    service_name: str = "qzdap-app",
    otlp_endpoint: str | None = None,
    sample_rate: float = 1.0,
) -> None:
    """Set up the global tracer provider.

    If `otlp_endpoint` is None, traces stay in-process (used in tests).
    """
    global _PROVIDER
    if _PROVIDER is not None:
        return

    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource, sampler=TraceIdRatioBased(sample_rate))

    if otlp_endpoint:
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
            OTLPSpanExporter,
        )

        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=otlp_endpoint))
        )

    trace.set_tracer_provider(provider)
    _PROVIDER = provider


def get_tracer(name: str = "qzdap") -> trace.Tracer:
    return trace.get_tracer(name)


def current_span() -> trace.Span | None:
    span = trace.get_current_span()
    return span if span is not trace.INVALID_SPAN else None


def shutdown_tracing() -> None:
    global _PROVIDER
    if _PROVIDER is not None:
        _PROVIDER.shutdown()
        _PROVIDER = None
