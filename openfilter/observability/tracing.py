"""
OpenTelemetry distributed tracing for OpenFilter pipeline execution.

Provides TracerProvider setup, parent trace context extraction from the
TRACEPARENT environment variable, and a span exporter factory that mirrors
the metrics ExporterFactory pattern.
"""

import os
import logging
from typing import Optional

from opentelemetry import context, trace
from opentelemetry.context.context import Context
from opentelemetry.propagate import extract
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
    SpanExporter,
)

logger = logging.getLogger(__name__)


def build_span_exporter(exporter_type: str, **config) -> SpanExporter:
    """Build a span exporter matching the metrics exporter factory pattern.

    Supported types: console, silent, otlp, otlp_grpc, otlp_http.
    """
    exporter_type = exporter_type.lower()

    if exporter_type == "console":
        return ConsoleSpanExporter()

    if exporter_type == "silent":
        from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult

        class SilentSpanExporter(SpanExporter):
            def export(self, spans):
                return SpanExportResult.SUCCESS

            def shutdown(self):
                pass

            def force_flush(self, timeout_millis=30000):
                return True

        return SilentSpanExporter()

    if exporter_type in ("otlp", "otlp_grpc"):
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
            OTLPSpanExporter as OTLPGrpcSpanExporter,
        )

        endpoint = (
            config.get("endpoint")
            or os.getenv("TELEMETRY_EXPORTER_OTLP_ENDPOINT")
            or os.getenv("OTEL_EXPORTER_OTLP_GRPC_ENDPOINT")
            or "http://localhost:4317"
        )
        # The Plainsight in-cluster collector and the upstream OTel collector
        # default to plaintext gRPC on 4317. The Python exporter defaults to TLS
        # unless told otherwise, which silently breaks every export with a TLS
        # handshake error. Mirror the Go services (otlptracegrpc.WithInsecure)
        # and opt out by default; operators who need TLS can pass insecure=False
        # via exporter_config.
        insecure = config.get("insecure", True)
        return OTLPGrpcSpanExporter(endpoint=endpoint, insecure=insecure)

    if exporter_type == "otlp_http":
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter as OTLPHttpSpanExporter,
        )

        endpoint = (
            config.get("endpoint")
            or os.getenv("OTEL_EXPORTER_OTLP_HTTP_ENDPOINT")
            or "http://localhost:4318"
        )
        return OTLPHttpSpanExporter(endpoint=endpoint)

    # Fall back to console
    logger.warning(
        "Unknown tracing exporter type %r, falling back to console", exporter_type
    )
    return ConsoleSpanExporter()


def extract_parent_context() -> Optional[Context]:
    """Extract parent trace context from the TRACEPARENT environment variable.

    The pipeline controller sets TRACEPARENT on the pod from the CR annotation
    ``traces.opentelemetry.io/traceparent``.  We use the W3C propagator to
    parse it into an OTel context so that all spans in this process are
    children of the orchestration trace.

    Returns the extracted context, or ``None`` if TRACEPARENT is not set.
    """
    traceparent = os.getenv("TRACEPARENT")
    if not traceparent:
        return None

    carrier = {"traceparent": traceparent}
    # Also pick up tracestate if available
    tracestate = os.getenv("TRACESTATE")
    if tracestate:
        carrier["tracestate"] = tracestate

    ctx = extract(carrier)
    logger.info("Extracted parent trace context from TRACEPARENT=%s", traceparent)
    return ctx


def setup_tracer_provider(
    resource: Resource,
    exporter_type: str = "silent",
    exporter_config: Optional[dict] = None,
) -> TracerProvider:
    """Create and register a TracerProvider sharing the same Resource as metrics.

    Args:
        resource: OTel Resource (reused from MeterProvider).
        exporter_type: Exporter type string (same values as metrics).
        exporter_config: Extra kwargs forwarded to the span exporter builder.

    Returns:
        The configured TracerProvider.
    """
    exporter_config = exporter_config or {}
    span_exporter = build_span_exporter(exporter_type, **exporter_config)
    processor = BatchSpanProcessor(span_exporter)

    provider = TracerProvider(resource=resource)
    provider.add_span_processor(processor)

    trace.set_tracer_provider(provider)
    logger.info(
        "TracerProvider initialised with %s exporter", exporter_type
    )
    return provider
