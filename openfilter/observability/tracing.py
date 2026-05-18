"""
OpenTelemetry distributed tracing for OpenFilter pipeline execution.

Provides TracerProvider setup, parent trace context extraction from the
TRACEPARENT environment variable, and a span exporter factory that mirrors
the metrics ExporterFactory pattern.
"""

import contextlib
import os
import logging
from typing import Iterator, Optional

from opentelemetry import context, trace
from opentelemetry.context.context import Context
from opentelemetry.propagate import extract
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
    SpanExporter,
    SpanExportResult,
)

from openfilter.observability._otlp import infer_otlp_insecure

logger = logging.getLogger(__name__)


_HOP_TRACER_NAME = "openfilter.filter_runtime.mq"
# Module-level tracer reference consulted by ``maybe_start_span``. Read on the
# hot path of every emitted hop sub-span; written only at ``MQ.__init__`` time.
#
# Concurrency model: writes are serialized in practice because every Filter
# process today constructs a single ``MQ`` (which calls ``register_hop_tracer``
# from the main thread before any worker thread starts emitting spans). Reads
# rely on the CPython GIL making the attribute fetch atomic. We deliberately
# do NOT lock around reads — adding lock overhead on every ``maybe_start_span``
# call would defeat the point of the helper's short-circuit behavior. If a
# future design ever runs multiple Filters in one process with different
# tracers, this is the place that needs revisiting: a lock would not fix the
# underlying "last writer wins" semantics, only paper over them.
_HOP_TRACER: Optional[trace.Tracer] = None


def register_hop_tracer(tracer: Optional[trace.Tracer]) -> None:
    """Register the tracer used by ``maybe_start_span`` for nested hop spans
    (``frame.encode_jpg`` / ``frame.decode_jpg`` / ``zmq.send_multipart`` /
    ``zmq.recv_multipart``). Called by ``MQ.__init__`` once the Filter has built
    its OpenTelemetryClient — without this, ``maybe_start_span`` would fall back to
    ``trace.get_tracer`` against the global provider, which is not set in unit
    tests that build their own provider locally."""
    global _HOP_TRACER
    _HOP_TRACER = tracer


@contextlib.contextmanager
def maybe_start_span(name: str, attributes: Optional[dict] = None) -> Iterator[None]:
    """Start a child span ONLY if there is already a recording span in the current context.

    Used for spans nested inside an outer ``mq.send`` / ``mq.recv`` (``frame.encode_jpg``,
    ``frame.decode_jpg``, ``zmq.send_multipart``, ``zmq.recv_multipart``): if the outer hop
    isn't being traced, this is a single ``is_recording()`` check and a no-op
    ``nullcontext`` — no Span object is allocated, no tracer lookup happens on the hot path.

    The gating condition for the OUTER hop span is the ``self.tracer`` attribute cached on
    ``MQ`` at init; that attribute is ``None`` when tracing is disabled, so no outer span
    means no recording context, which means this helper short-circuits cleanly.
    """
    current = trace.get_current_span()
    if not current.is_recording():
        yield
        return
    tracer = _HOP_TRACER or trace.get_tracer(_HOP_TRACER_NAME)
    with tracer.start_as_current_span(name, attributes=attributes or None):
        yield


class SilentSpanExporter(SpanExporter):
    """No-op exporter that accepts and discards all spans.

    Promoted to module level so it's importable and discoverable (the
    metrics side does the same with ``SilentMetricExporter``).
    """

    def export(self, spans):
        return SpanExportResult.SUCCESS

    def shutdown(self):
        pass

    def force_flush(self, timeout_millis=30000):
        return True


def build_span_exporter(exporter_type: str, **config) -> SpanExporter:
    """Build a span exporter matching the metrics exporter factory pattern.

    Supported types: console, silent, otlp, otlp_grpc, otlp_http.
    """
    exporter_type = exporter_type.lower()

    if exporter_type == "console":
        return ConsoleSpanExporter()

    if exporter_type == "silent":
        return SilentSpanExporter()

    if exporter_type in ("otlp", "otlp_grpc"):
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
            OTLPSpanExporter as OTLPGrpcSpanExporter,
        )

        # Endpoint precedence:
        #   1. Explicit config kwarg
        #   2. TELEMETRY_EXPORTER_OTLP_ENDPOINT (Plainsight convention,
        #      matches metrics factory)
        #   3. OTEL_EXPORTER_OTLP_ENDPOINT (standard OTel env var)
        #   4. OTEL_EXPORTER_OTLP_GRPC_ENDPOINT (non-standard, kept for
        #      backward compat — not part of the OTel spec)
        #   5. localhost:4317 fallback
        endpoint = (
            config.get("endpoint")
            or os.getenv("TELEMETRY_EXPORTER_OTLP_ENDPOINT")
            or os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
            or os.getenv("OTEL_EXPORTER_OTLP_GRPC_ENDPOINT")
            or "http://localhost:4317"
        )
        # Infer TLS from the endpoint scheme: http:// is plaintext, https:// or
        # bare host:port is TLS. An explicit insecure= in exporter_config wins
        # — operators pointing a bare-host:port endpoint at a plaintext
        # collector still need to pass insecure=True.
        insecure = config.get("insecure")
        if insecure is None:
            insecure = infer_otlp_insecure(endpoint)
        return OTLPGrpcSpanExporter(endpoint=endpoint, insecure=insecure)

    if exporter_type == "otlp_http":
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter as OTLPHttpSpanExporter,
        )

        endpoint = (
            config.get("endpoint")
            or os.getenv("TELEMETRY_EXPORTER_OTLP_ENDPOINT")
            or os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
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
    set_global: bool = True,
) -> TracerProvider:
    """Create and optionally register a TracerProvider sharing the same Resource as metrics.

    Args:
        resource: OTel Resource (reused from MeterProvider).
        exporter_type: Exporter type string (same values as metrics).
        exporter_config: Extra kwargs forwarded to the span exporter builder.
        set_global: When True (default), call ``trace.set_tracer_provider()``
            to register as the process-global provider. Set to False if the
            host application manages its own TracerProvider and you want to
            avoid mutating global OTel state.

    Returns:
        The configured TracerProvider.
    """
    exporter_config = exporter_config or {}
    span_exporter = build_span_exporter(exporter_type, **exporter_config)
    processor = BatchSpanProcessor(span_exporter)

    provider = TracerProvider(resource=resource)
    provider.add_span_processor(processor)

    if set_global:
        trace.set_tracer_provider(provider)
    logger.info(
        "TracerProvider initialised with %s exporter (global=%s)",
        exporter_type,
        set_global,
    )
    return provider
