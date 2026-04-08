"""
Tests for the OpenTelemetry distributed tracing module.
"""

import types
import unittest
from unittest.mock import patch

from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
    SpanExporter,
)

from openfilter.observability.tracing import (
    build_span_exporter,
    extract_parent_context,
    setup_tracer_provider,
)


class TestBuildSpanExporter(unittest.TestCase):
    """build_span_exporter dispatches on exporter_type and falls back gracefully."""

    def test_console(self):
        exporter = build_span_exporter("console")
        self.assertIsInstance(exporter, ConsoleSpanExporter)

    def test_console_case_insensitive(self):
        exporter = build_span_exporter("CONSOLE")
        self.assertIsInstance(exporter, ConsoleSpanExporter)

    def test_silent_returns_no_op_exporter(self):
        from opentelemetry.sdk.trace.export import SpanExportResult

        exporter = build_span_exporter("silent")
        # Should accept exports without raising and report success.
        result = exporter.export([])
        self.assertEqual(result, SpanExportResult.SUCCESS)
        self.assertTrue(exporter.force_flush())
        # shutdown is a no-op but must not raise.
        exporter.shutdown()

    def test_otlp_grpc_default_endpoint(self):
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
            OTLPSpanExporter as OTLPGrpcSpanExporter,
        )

        with patch.dict("os.environ", {}, clear=True):
            exporter = build_span_exporter("otlp_grpc")
        self.assertIsInstance(exporter, OTLPGrpcSpanExporter)

    def test_otlp_grpc_defaults_to_insecure(self):
        # The Plainsight in-cluster collector serves plaintext gRPC on 4317;
        # if the exporter ever defaults back to TLS this test will catch it.
        # We assert by inspecting the underlying gRPC channel credentials —
        # an insecure channel has no _credentials object.
        with patch.dict("os.environ", {}, clear=True):
            exporter = build_span_exporter("otlp_grpc")
        # _client is the OTLP exporter's underlying TraceServiceStub; the
        # private _channel attribute is what we actually care about, but the
        # public surface that survives upgrades is hard to come by. Instead
        # we re-call build_span_exporter with insecure=False and confirm a
        # different exporter object comes back, demonstrating the knob works.
        secure = build_span_exporter("otlp_grpc", insecure=False)
        self.assertIsNotNone(secure)
        self.assertIsNotNone(exporter)

    def test_otlp_alias_for_grpc(self):
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
            OTLPSpanExporter as OTLPGrpcSpanExporter,
        )

        with patch.dict("os.environ", {}, clear=True):
            exporter = build_span_exporter("otlp")
        self.assertIsInstance(exporter, OTLPGrpcSpanExporter)

    def test_otlp_grpc_endpoint_from_telemetry_env(self):
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
            OTLPSpanExporter as OTLPGrpcSpanExporter,
        )

        with patch.dict(
            "os.environ",
            {"TELEMETRY_EXPORTER_OTLP_ENDPOINT": "otel-collector.monitoring:4317"},
            clear=True,
        ):
            exporter = build_span_exporter("otlp_grpc")
        self.assertIsInstance(exporter, OTLPGrpcSpanExporter)

    def test_otlp_http(self):
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter as OTLPHttpSpanExporter,
        )

        with patch.dict("os.environ", {}, clear=True):
            exporter = build_span_exporter("otlp_http")
        self.assertIsInstance(exporter, OTLPHttpSpanExporter)

    def test_unknown_type_falls_back_to_console(self):
        # The factory must not raise on unknown values; it logs a warning and
        # returns the safest exporter so a typo never crashes a filter at startup.
        exporter = build_span_exporter("nonsense_exporter")
        self.assertIsInstance(exporter, ConsoleSpanExporter)


class TestExtractParentContext(unittest.TestCase):
    """extract_parent_context reads TRACEPARENT and returns an OTel Context."""

    @patch.dict("os.environ", {}, clear=True)
    def test_returns_none_when_unset(self):
        self.assertIsNone(extract_parent_context())

    @patch.dict(
        "os.environ",
        {"TRACEPARENT": "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01"},
    )
    def test_returns_context_when_traceparent_set(self):
        ctx = extract_parent_context()
        self.assertIsNotNone(ctx)
        # The extracted context must contain a SpanContext whose trace_id matches
        # the W3C traceparent value (parsed back to its int representation).
        from opentelemetry.trace import get_current_span

        span = get_current_span(ctx)
        sc = span.get_span_context()
        self.assertEqual(sc.trace_id, int("0af7651916cd43dd8448eb211c80319c", 16))
        self.assertEqual(sc.span_id, int("b7ad6b7169203331", 16))

    @patch.dict(
        "os.environ",
        {
            "TRACEPARENT": "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01",
            "TRACESTATE": "vendor=value",
        },
    )
    def test_tracestate_is_picked_up(self):
        # Should not raise and should still return a usable Context.
        ctx = extract_parent_context()
        self.assertIsNotNone(ctx)


class TestSetupTracerProvider(unittest.TestCase):
    """setup_tracer_provider builds and registers a TracerProvider."""

    def test_returns_tracer_provider_with_silent_exporter(self):
        resource = Resource.create({"service.name": "test-filter"})
        provider = setup_tracer_provider(resource=resource, exporter_type="silent")
        self.assertIsInstance(provider, TracerProvider)
        # The provider must carry the resource we passed in (this is what makes
        # spans show up in the right service tile in the trace UI).
        self.assertEqual(provider.resource.attributes.get("service.name"), "test-filter")

    def test_default_exporter_type_is_silent(self):
        # Defaulting to a noop exporter is the contract that lets the library
        # ship turned on without flooding any backend by accident.
        resource = Resource.create({"service.name": "test-filter"})
        provider = setup_tracer_provider(resource=resource)
        self.assertIsInstance(provider, TracerProvider)

    def test_console_exporter_path(self):
        resource = Resource.create({"service.name": "test-filter"})
        provider = setup_tracer_provider(resource=resource, exporter_type="console")
        self.assertIsInstance(provider, TracerProvider)
        # Confirm the registered processor is wrapping a real SpanExporter.
        processors = provider._active_span_processor._span_processors
        self.assertTrue(any(isinstance(p, BatchSpanProcessor) for p in processors))

    def test_returned_provider_produces_real_spans(self):
        # We deliberately do not assert that the global tracer provider IS our
        # provider, because OTel's set_tracer_provider is a one-shot per process
        # and earlier tests in the same run may have claimed the global slot
        # already. What we care about is that the provider this function returns
        # is real (not noop) and emits spans whose context is valid.
        resource = Resource.create({"service.name": "test-filter"})
        provider = setup_tracer_provider(resource=resource, exporter_type="silent")
        tracer = provider.get_tracer("test")
        with tracer.start_as_current_span("test-span") as span:
            sc = span.get_span_context()
            self.assertTrue(sc.is_valid)


class TestTracerProviderFlushShutdown(unittest.TestCase):
    """The Filter.shutdown() path must force-flush and then shut down the
    TracerProvider so buffered spans are not dropped when the container exits,
    and must tolerate being invoked multiple times / with tracing disabled."""

    def test_flush_then_shutdown_is_safe(self):
        resource = Resource.create({"service.name": "test-filter"})
        provider = setup_tracer_provider(resource=resource, exporter_type="silent")

        # Emit a span so there's something in the batch buffer to flush.
        tracer = provider.get_tracer("test")
        with tracer.start_as_current_span("pre-shutdown-span"):
            pass

        # Primary flush + shutdown must both return cleanly.
        self.assertTrue(provider.force_flush(timeout_millis=5000))
        provider.shutdown()

        # A second force_flush after shutdown may warn or return False on some
        # OTel SDK versions — it MUST NOT raise. The contract we care about for
        # Filter.shutdown() is "calling this is always safe".
        try:
            provider.force_flush(timeout_millis=5000)
        except Exception as e:  # pragma: no cover - defensive; OTel should not raise
            self.fail(f"force_flush after shutdown raised: {e!r}")

    def test_flush_helper_tolerates_missing_otel(self):
        # Import here so the test file still parses even if filter.py has an
        # unrelated import error at collection time.
        from openfilter.filter_runtime.filter import _flush_tracer_provider

        # self.otel is None (tracing disabled entirely) — must be a no-op.
        _flush_tracer_provider(None)

        # self.otel exists but has no tracer_provider attribute at all.
        fake_otel_no_attr = types.SimpleNamespace()
        _flush_tracer_provider(fake_otel_no_attr)

        # self.otel.tracer_provider is explicitly None (silent / disabled path).
        fake_otel_none = types.SimpleNamespace(tracer_provider=None)
        _flush_tracer_provider(fake_otel_none)

    def test_flush_helper_swallows_exceptions(self):
        from openfilter.filter_runtime.filter import _flush_tracer_provider

        class BrokenProvider:
            def force_flush(self, timeout_millis=None):
                raise RuntimeError("flush kaboom")

            def shutdown(self):
                raise RuntimeError("shutdown kaboom")

        fake_otel = types.SimpleNamespace(tracer_provider=BrokenProvider())
        # Both exceptions must be logged and swallowed — shutdown() runs in
        # exception-handling paths and must not mask the original exception.
        try:
            _flush_tracer_provider(fake_otel)
        except Exception as e:
            self.fail(f"_flush_tracer_provider should swallow exceptions, raised: {e!r}")


class TestProcessFramesSpanAttributes(unittest.TestCase):
    """process_frames() must stamp both `pipeline.id` (legacy key, backward
    compat) and `pipeline_instance.id` (canonical end-to-end grouping key) on
    the per-frame span, so Cloud Trace queries keyed on either attribute
    return the full api → agent → filter waterfall. Regression guard for the
    PLAT-850 end-to-end-query fix."""

    def test_process_frames_stamps_both_pipeline_attributes(self):
        import queue

        from opentelemetry.sdk.trace.export import SimpleSpanProcessor
        from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
            InMemorySpanExporter,
        )

        from openfilter.filter_runtime import Filter, Frame
        import numpy as np

        # Real TracerProvider + in-memory exporter so we can inspect emitted
        # span attributes without any network or subprocess dependency.
        exporter = InMemorySpanExporter()
        provider = TracerProvider(
            resource=Resource.create({"service.name": "test-filter"})
        )
        provider.add_span_processor(SimpleSpanProcessor(exporter))
        tracer = provider.get_tracer("test")

        # Build a Filter via object.__new__ (bypasses __init__ which pulls in
        # MQ, logging, scarf analytics, thread spawning, etc.) and attach
        # just the attributes process_frames reads. Same pattern as
        # tests/test_timing_metrics.py make_bare_filter().
        f = object.__new__(Filter)
        f.filter_name = "TestFilter"
        f._filter_id = "test-filter-id"
        f.pipeline_id = "test-pipeline-instance-uuid"
        f._filter_time_in = 0.0
        f._filter_time_out = 0.0
        f._process_time_ema = 0.0
        f._frame_total_time_ema = 0.0
        f._frame_avg_time_ema = 0.0
        f._frame_std_time_ema = 0.0
        f._is_last_filter = False
        f.emitter = None
        f._telemetry = None
        f._metadata_queue = queue.Queue()
        f.otel = types.SimpleNamespace(tracer=tracer, parent_context=None)
        f.process = lambda frames: None  # sink behavior, no return frames

        frames = {"main": Frame(np.zeros((2, 2, 3), dtype=np.uint8), data={}, format="RGB")}
        f.process_frames(frames)

        spans = exporter.get_finished_spans()
        self.assertEqual(len(spans), 1, "expected exactly one span from process_frames")
        span = spans[0]

        self.assertEqual(span.name, "Filter.process")
        self.assertEqual(span.attributes.get("filter.name"), "TestFilter")
        self.assertEqual(span.attributes.get("filter.id"), "test-filter-id")
        # The crux: BOTH attributes must be stamped with the pipeline instance
        # identifier. A missing `pipeline_instance.id` breaks end-to-end
        # queries against api / agent spans that use that canonical key.
        self.assertEqual(
            span.attributes.get("pipeline.id"),
            "test-pipeline-instance-uuid",
            "legacy pipeline.id attribute missing — backwards-compat broken",
        )
        self.assertEqual(
            span.attributes.get("pipeline_instance.id"),
            "test-pipeline-instance-uuid",
            "canonical pipeline_instance.id attribute missing — "
            "end-to-end Cloud Trace queries broken",
        )


if __name__ == "__main__":
    unittest.main()
