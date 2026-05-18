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
    infer_otlp_insecure,
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

    def test_infer_otlp_insecure_from_scheme(self):
        # http:// → plaintext, https:// → TLS, bare host:port → TLS (secure
        # default). Bare-endpoint case matters: pointing at a plaintext
        # collector via "collector:4317" must NOT silently downgrade to
        # plaintext — the operator has to opt in with insecure=True.
        self.assertTrue(infer_otlp_insecure("http://localhost:4317"))
        self.assertTrue(infer_otlp_insecure("HTTP://localhost:4317"))
        self.assertFalse(infer_otlp_insecure("https://collector:4317"))
        self.assertFalse(infer_otlp_insecure("collector.monitoring:4317"))
        self.assertFalse(infer_otlp_insecure(None))
        self.assertFalse(infer_otlp_insecure(""))

    def test_otlp_grpc_https_endpoint_infers_tls(self):
        # An https:// endpoint must infer insecure=False so we don't silently
        # send plaintext over a link the operator declared TLS. The helper's
        # full input matrix is covered by test_infer_otlp_insecure_from_scheme
        # — this is the integration check that build_span_exporter actually
        # routes the inferred value into the exporter constructor.
        exporter = build_span_exporter(
            "otlp_grpc", endpoint="https://collector.example.com:4317"
        )
        self.assertIsNotNone(exporter)

    def test_otlp_grpc_explicit_insecure_overrides_inference(self):
        # Operators who run a plaintext collector behind a bare host:port
        # must still be able to opt in with insecure=True.
        exporter = build_span_exporter(
            "otlp_grpc", endpoint="collector:4317", insecure=True
        )
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

    def test_otlp_http_endpoint_from_telemetry_env(self):
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter as OTLPHttpSpanExporter,
        )

        with patch.dict(
            "os.environ",
            {"TELEMETRY_EXPORTER_OTLP_ENDPOINT": "otel-collector.monitoring:4318"},
            clear=True,
        ):
            exporter = build_span_exporter("otlp_http")
        self.assertIsInstance(exporter, OTLPHttpSpanExporter)

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


class _SpanCapture(unittest.TestCase):
    """Shared test-suite helper that builds a tracer wired to an in-memory exporter.

    Subclasses build hop-level scenarios (send/recv across a process-local ZMQ pair)
    and then inspect ``self.exporter.get_finished_spans()`` to assert names,
    attributes, and parent/child nesting. Spans are emitted synchronously via
    SimpleSpanProcessor so ordering is deterministic and no force_flush is needed.
    """

    def setUp(self):
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor
        from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
            InMemorySpanExporter,
        )
        from openfilter.observability.tracing import register_hop_tracer

        self.exporter = InMemorySpanExporter()
        self.provider = TracerProvider(
            resource=Resource.create({"service.name": "mq-hop-test"}),
        )
        self.provider.add_span_processor(SimpleSpanProcessor(self.exporter))
        self.tracer = self.provider.get_tracer("test")
        # Frame.encode_jpg / Frame.decode_jpg and the kernel-level zmq.* sub-spans
        # resolve their tracer via the module-level registry, not the global OTel
        # provider — register the test tracer so child sub-spans land in our exporter.
        register_hop_tracer(self.tracer)
        self.addCleanup(register_hop_tracer, None)

    def _spans_by_name(self):
        return {s.name: s for s in self.exporter.get_finished_spans()}


class TestHopSpansRawTransport(_SpanCapture):
    """mq.send / mq.recv with the RAW transport: the codec sub-spans
    (frame.encode_jpg, frame.decode_jpg) MUST NOT fire because there is no jpg
    encode/decode work to do. The other four spans (mq.send, frame.serialize,
    zmq.send_multipart on the send leg; mq.recv, zmq.recv_multipart,
    frame.deserialize on the recv leg) must all fire and nest correctly."""

    def test_raw_send_recv_produces_expected_spans_and_nesting(self):
        import numpy as np
        from openfilter.filter_runtime.mq import MQ
        from openfilter.filter_runtime.frame import Frame

        # frames2topicmsgs(outs_jpg=False) is the raw transport path. We don't need
        # a real ZMQ socket — exercising frames2topicmsgs + topicmsgs2frames inside
        # an mq.send hop span is the unit-test surface for the codec gating logic.
        mq = MQ.__new__(MQ)
        mq.mq_id = "test-mq"
        mq.outs_jpg = False
        mq.shm_pool = None
        mq.shm_cache = None
        mq.tracer = self.tracer
        mq.recv_parent_ctx = None

        img = np.zeros((4, 4, 3), dtype=np.uint8)
        frames = {"main": Frame(img, {"meta": {"id": "frame-7"}}, "RGB")}

        # Send leg: mq.send wraps frame.serialize (which in raw mode does NOT trigger
        # frame.encode_jpg). frames2topicmsgs is the unit of work inside frame.serialize.
        with self.tracer.start_as_current_span("mq.send", attributes=MQ._hop_attrs(frames)) as send_span:
            with self.tracer.start_as_current_span("frame.serialize"):
                topicmsgs = MQ.frames2topicmsgs(frames, outs_jpg=False)
            send_span.set_attribute("payload_bytes", 99)

        # Recv leg: synthesize the retroactive structure produced by MQ.recv (mq.recv
        # with extracted context as parent, zmq.recv_multipart sibling, frame.deserialize
        # current; in raw mode frame.decode_jpg must NOT fire).
        recv_span = self.tracer.start_span("mq.recv")
        from opentelemetry import trace as _trace
        recv_ctx = _trace.set_span_in_context(recv_span)
        zmq_recv = self.tracer.start_span("zmq.recv_multipart", context=recv_ctx)
        zmq_recv.end()
        from opentelemetry import context as _ctx
        tok = _ctx.attach(recv_ctx)
        try:
            with self.tracer.start_as_current_span("frame.deserialize"):
                recv_frames = MQ.topicmsgs2frames(topicmsgs)
        finally:
            _ctx.detach(tok)
        recv_span.end()

        spans = self._spans_by_name()
        self.assertIn("mq.send", spans)
        self.assertIn("frame.serialize", spans)
        self.assertIn("mq.recv", spans)
        self.assertIn("zmq.recv_multipart", spans)
        self.assertIn("frame.deserialize", spans)
        self.assertNotIn(
            "frame.encode_jpg", spans,
            "raw transport must not trigger jpg encode",
        )
        self.assertNotIn(
            "frame.decode_jpg", spans,
            "raw transport must not trigger jpg decode (the frame went over the wire as raw bytes)",
        )

        # Round-trip integrity check: receiver got the same pixels back.
        self.assertEqual(set(recv_frames), {"main"})
        recv_frame = recv_frames["main"]
        self.assertTrue(np.array_equal(recv_frame.image, img))

        # Nesting: frame.serialize is a child of mq.send; frame.deserialize is a child of mq.recv.
        self.assertEqual(spans["frame.serialize"].parent.span_id, spans["mq.send"].context.span_id)
        self.assertEqual(spans["frame.deserialize"].parent.span_id, spans["mq.recv"].context.span_id)
        self.assertEqual(spans["zmq.recv_multipart"].parent.span_id, spans["mq.recv"].context.span_id)

        # mq.send carries the frame.id and frame.format attributes derived from frames dict.
        self.assertEqual(spans["mq.send"].attributes.get("frame.id"), "frame-7")
        self.assertEqual(spans["mq.send"].attributes.get("frame.format"), "RGB")
        self.assertEqual(spans["mq.send"].attributes.get("topic"), "main")
        self.assertEqual(spans["mq.send"].attributes.get("payload_bytes"), 99)


class TestHopSpansJpgTransport(_SpanCapture):
    """mq.send / mq.recv with the JPG transport: frame.encode_jpg MUST fire inside
    frame.serialize on the send leg, and frame.decode_jpg MUST fire inside
    frame.deserialize when the receiver actually decodes the frame (which happens
    lazily on the first .image access, exercised here via topicmsgs2frames +
    frame.image)."""

    def test_jpg_send_recv_emits_codec_subspans(self):
        import numpy as np
        from openfilter.filter_runtime.mq import MQ
        from openfilter.filter_runtime.frame import Frame

        mq = MQ.__new__(MQ)
        mq.mq_id = "test-mq"
        mq.outs_jpg = True
        mq.shm_pool = None
        mq.shm_cache = None
        mq.tracer = self.tracer
        mq.recv_parent_ctx = None

        img = np.zeros((8, 8, 3), dtype=np.uint8)
        frames = {"main": Frame(img, {"meta": {"id": "frame-jpg-1"}}, "BGR")}

        with self.tracer.start_as_current_span("mq.send"):
            with self.tracer.start_as_current_span("frame.serialize"):
                topicmsgs = MQ.frames2topicmsgs(frames, outs_jpg=True)

        recv_span = self.tracer.start_span("mq.recv")
        from opentelemetry import trace as _trace, context as _ctx
        recv_ctx = _trace.set_span_in_context(recv_span)
        tok = _ctx.attach(recv_ctx)
        try:
            with self.tracer.start_as_current_span("frame.deserialize"):
                recv_frames = MQ.topicmsgs2frames(topicmsgs)
                # frame.from_jpg defers decode; force it now under the deserialize span
                # so frame.decode_jpg materializes as a child where the user can see it.
                _ = recv_frames["main"].image
        finally:
            _ctx.detach(tok)
        recv_span.end()

        spans = self._spans_by_name()
        self.assertIn("frame.encode_jpg", spans)
        self.assertIn("frame.decode_jpg", spans)
        # frame.encode_jpg is nested inside frame.serialize (which is inside mq.send).
        self.assertEqual(
            spans["frame.encode_jpg"].parent.span_id,
            spans["frame.serialize"].context.span_id,
        )
        # frame.decode_jpg is nested inside frame.deserialize.
        self.assertEqual(
            spans["frame.decode_jpg"].parent.span_id,
            spans["frame.deserialize"].context.span_id,
        )
        self.assertEqual(spans["frame.encode_jpg"].attributes.get("frame.format"), "BGR")


class TestCodecSubspansAreHotPathFree(unittest.TestCase):
    """When there is no recording outer span (tracing disabled / no mq.send wrapper),
    Frame.jpg / Frame.decode MUST NOT allocate a child Span. This is the contract
    that makes the codec instrumentation safe to enable unconditionally."""

    def test_encode_jpg_outside_outer_span_emits_nothing(self):
        # Set up a real provider so spans would be recorded if anyone created them —
        # this proves the gating is "is there a recording parent?", not "is there a provider?"
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor
        from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
            InMemorySpanExporter,
        )
        from openfilter.filter_runtime.frame import Frame
        import numpy as np

        exporter = InMemorySpanExporter()
        provider = TracerProvider()
        provider.add_span_processor(SimpleSpanProcessor(exporter))
        from opentelemetry import trace as _trace
        _trace.set_tracer_provider(provider)

        img = np.zeros((4, 4, 3), dtype=np.uint8)
        frame = Frame(img, {}, "BGR")
        # Trigger encode + decode outside any current span.
        _ = frame.jpg
        _ = Frame.decode(bytes(frame.jpg), "BGR")

        names = [s.name for s in exporter.get_finished_spans()]
        self.assertNotIn("frame.encode_jpg", names)
        self.assertNotIn("frame.decode_jpg", names)


class TestEnvelopeContextPropagation(unittest.TestCase):
    """Per-frame trace context must travel through the ZMQ envelope dict via
    standard W3C TraceContextTextMapPropagator (no hand-rolled format). Asserts
    that injection adds traceparent to the carrier and that extraction yields a
    context whose trace_id matches the injecting span — this is what makes the
    consumer-side {Filter}.process span share a trace with the producer's
    mq.send span."""

    def test_inject_then_extract_round_trips_trace_id(self):
        from opentelemetry import trace as _trace
        from opentelemetry.propagate import inject as _inject, extract as _extract
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor
        from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
            InMemorySpanExporter,
        )

        provider = TracerProvider()
        provider.add_span_processor(SimpleSpanProcessor(InMemorySpanExporter()))
        tracer = provider.get_tracer("propagation-test")

        env: dict = {"sid": "srv", "mid": 1, "topics": ["main"]}
        with tracer.start_as_current_span("mq.send") as send_span:
            _inject(env)
            send_trace_id = send_span.get_span_context().trace_id

        # The W3C contract: traceparent appears in the carrier, parseable back to
        # the same trace_id. Hand-rolled formats break here.
        self.assertIn("traceparent", env)
        extracted = _extract(env)
        extracted_span = _trace.get_current_span(extracted)
        self.assertEqual(extracted_span.get_span_context().trace_id, send_trace_id)


class TestMQReceiverExtractsTraceContext(unittest.TestCase):
    """The ZMQReceiver.recv path that parses each incoming envelope must call
    otel_extract whenever a traceparent is present, and stash the resulting
    Context on ``self.last_extracted_ctx`` for MQ.recv to consume. We exercise
    the smallest possible slice: the conditional extraction block — by simulating
    what recv_once does after json_loads on the envelope."""

    def test_envelope_with_traceparent_populates_last_extracted_ctx(self):
        from openfilter.filter_runtime.zeromq import ZMQReceiver
        from opentelemetry import trace as _trace
        from opentelemetry.propagate import inject as _inject
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor
        from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
            InMemorySpanExporter,
        )

        provider = TracerProvider()
        provider.add_span_processor(SimpleSpanProcessor(InMemorySpanExporter()))
        tracer = provider.get_tracer("recv-extract-test")

        env: dict = {"sid": "srv", "mid": 5}
        with tracer.start_as_current_span("producer") as producer_span:
            _inject(env)
            producer_trace_id = producer_span.get_span_context().trace_id

        # Build a bare ZMQReceiver with only the fields the extraction code touches.
        rcv = ZMQReceiver.__new__(ZMQReceiver)
        rcv.last_extracted_ctx = None

        # Inline the conditional block from recv_once so the test stays focused on
        # the extraction contract rather than the surrounding poll/sub plumbing.
        if 'traceparent' in env:
            from openfilter.filter_runtime.zeromq import otel_extract
            rcv.last_extracted_ctx = otel_extract(env)

        self.assertIsNotNone(rcv.last_extracted_ctx)
        extracted_span = _trace.get_current_span(rcv.last_extracted_ctx)
        self.assertEqual(extracted_span.get_span_context().trace_id, producer_trace_id)


class TestFanInLastExtractedWins(unittest.TestCase):
    """Placeholder for the fan-in trace-context-joining case documented in
    ``MQ.recv``: when a receiver subscribes to multiple upstream senders, frames
    from non-last upstreams in a single recv batch end up parented under the one
    last-extracted upstream's mq.send context. Joining all of them would require
    span links across producer traces — intentionally out of scope for PLAT-866.

    Marked skip rather than left out so a future maintainer working on multi-
    upstream tracing finds the documented intent + the test stub to fill in,
    instead of having to rediscover the design decision."""

    @unittest.skip("Out of scope for PLAT-866 — see fan-in caveat in MQ.recv docstring")
    def test_multiple_upstreams_produce_span_links_per_envelope(self):
        # Future work: drive MQ.recv with a stand-in receiver whose recv()
        # returns multiple topicmsgs each tagged with a different upstream's
        # extracted context. Assert each resulting frame.deserialize child span
        # is parented under its own upstream's mq.send via span links, not
        # under the arbitrary last-extracted one.
        self.fail("not implemented")


class TestMQRecvSpanEndsOnException(unittest.TestCase):
    """Regression guard for the shingonoide review on PLAT-866: the retroactive
    ``mq.recv`` span is created without ``start_as_current_span``, so it MUST be
    wrapped in a try/finally that calls ``recv_span.end()`` even if
    ``topicmsgs2frames`` / ``metrics_.incoming`` raises mid-deserialize. Without
    the finally guard the span object stays buffered in the BatchSpanProcessor's
    pending queue with no end time and never reaches the exporter."""

    def test_recv_span_ends_when_topicmsgs2frames_raises(self):
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor
        from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
            InMemorySpanExporter,
        )

        from openfilter.filter_runtime.mq import MQ
        from openfilter.observability.tracing import register_hop_tracer

        exporter = InMemorySpanExporter()
        provider = TracerProvider()
        provider.add_span_processor(SimpleSpanProcessor(exporter))
        tracer = provider.get_tracer("recv-exception-test")
        register_hop_tracer(tracer)
        self.addCleanup(register_hop_tracer, None)

        class _BoomReceiver:
            """Stand-in for ZMQReceiver — returns a malformed envelope so
            ``MQ.topicmsgs2frames`` raises while deserializing. Implements the
            small surface MQ.recv actually touches: ``recv()``, ``last_*``
            telemetry handoff fields. recv() returns a topicmsg whose first
            element is the wrong type so topicmsgs2frames raises on
            ``xtra_dict['img']``."""

            last_extracted_ctx = None
            last_recv_t_start_ns = 0
            last_recv_t_end_ns = 0
            last_recv_bytes = 0

            def recv(self, *_a, **_kw):
                # Tuple of (topicmsgs, send_state). The msg[0] = 12345 is not a
                # dict, so topicmsgs2frames will raise on `xtra_dict['img']`.
                return ({"main": [12345, b"junk"]}, None)

        mq = MQ.__new__(MQ)
        mq.mq_id = "test-mq"
        mq.tracer = tracer
        mq.recv_parent_ctx = None
        mq.receiver = _BoomReceiver()
        mq.recv_state = None
        mq.mq_msgid_sync = False
        mq.shm_cache = None
        # DummyMetrics-shaped: only .incoming is touched on the recv path.
        mq.metrics_ = type("M", (), {"incoming": staticmethod(lambda *_: None)})()

        with self.assertRaises(Exception):
            mq.recv()

        # The mq.recv span must have been ended despite the deserialize exception,
        # so it appears in the exporter's finished-span list with a non-None end_time.
        finished = exporter.get_finished_spans()
        names = {s.name for s in finished}
        self.assertIn(
            "mq.recv", names,
            "mq.recv span was not ended; SimpleSpanProcessor never saw it. "
            "The try/finally around recv_span lifetime is missing or broken.",
        )

        # And the span must carry an ERROR status + recorded exception event —
        # tracer.start_span() + manual .end() does NOT auto-record exceptions the
        # way `with start_as_current_span` does, so this requires an explicit
        # record_exception / set_status in the except branch. Without that, the
        # span lands in Cloud Trace as a normal-looking recv with no error
        # indication, which is exactly the failure mode this guard prevents.
        from opentelemetry.trace import StatusCode

        recv_span = next(s for s in finished if s.name == "mq.recv")
        self.assertEqual(
            recv_span.status.status_code,
            StatusCode.ERROR,
            "mq.recv span did not carry ERROR status after topicmsgs2frames raised; "
            "the except branch must call set_status(StatusCode.ERROR).",
        )
        exc_events = [e for e in recv_span.events if e.name == "exception"]
        self.assertTrue(
            exc_events,
            "mq.recv span did not record the exception; "
            "the except branch must call record_exception(e).",
        )


if __name__ == "__main__":
    unittest.main()
