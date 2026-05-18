"""
Integration test for openfilter's OTLP gRPC trace export.

Upstreamed from the PLAT-827 multi-repo integration harness. Spins up
jaeger-all-in-one (via the module-scoped fixture in conftest.py), calls
setup_tracer_provider with the OTLP gRPC exporter pointed at jaeger,
emits a parent and child span, force-flushes the BatchSpanProcessor,
then polls the jaeger query API until the trace is visible and asserts
our service.name contributed spans to it.

Marked @pytest.mark.slow so the default `make test` run (which uses
-m "not slow") skips it. Run with:

    make test-integration

or equivalently:

    pytest -m slow tests/integration/

Requires docker on the local machine (or CI runner).
"""

from __future__ import annotations

import re

import pytest
from opentelemetry.sdk.resources import Resource

from openfilter.observability.tracing import setup_tracer_provider

SERVICE_NAME = "openfilter-integration-test"

TRACE_ID_RE = re.compile(r"^[0-9a-f]{32}$")


@pytest.mark.slow
def test_otlp_grpc_export_reaches_jaeger(jaeger):
    """Full round-trip: build tracer -> emit spans -> force-flush -> query.

    Exercises the exact code path openfilter pods run in production when
    the controller has injected TELEMETRY_EXPORTER_TYPE=otlp_grpc and
    TELEMETRY_EXPORTER_OTLP_ENDPOINT=otel-collector...:4317. The only
    production difference is the collector endpoint.
    """
    resource = Resource.create({"service.name": SERVICE_NAME})

    provider = setup_tracer_provider(
        resource=resource,
        exporter_type="otlp_grpc",
        exporter_config={"endpoint": jaeger.otlp_grpc_endpoint},
    )
    tracer = provider.get_tracer("openfilter-integration-test")

    with tracer.start_as_current_span("integration.parent") as parent:
        sc = parent.get_span_context()
        trace_id_hex = f"{sc.trace_id:032x}"
        with tracer.start_as_current_span("integration.child"):
            pass

    # BatchSpanProcessor buffers — force_flush is the contract that gets
    # spans out of the buffer and onto the wire before we query.
    provider.force_flush(timeout_millis=5000)
    provider.shutdown()

    assert TRACE_ID_RE.match(trace_id_hex), f"malformed trace_id: {trace_id_hex!r}"

    services = jaeger.wait_for_trace(trace_id_hex, timeout_secs=10.0)
    assert services, f"jaeger never saw trace {trace_id_hex}"
    assert SERVICE_NAME in services, (
        f"expected service.name={SERVICE_NAME!r} in jaeger trace {trace_id_hex}, "
        f"got {services!r}"
    )


@pytest.mark.slow
def test_per_frame_trace_context_crosses_mq_hop(jaeger, tmp_path):
    """Two MQ endpoints across an IPC hop must produce spans for the same frame.id
    that share a single trace ID and nest under the producer's mq.send span.

    This is the PLAT-866 acceptance criterion for per-frame distributed traces:
    PLAT-848's TRACEPARENT-from-env approach gave every frame the same parent,
    which meant filter A's frame-17 spans were not linked to filter B's frame-17
    spans. With per-frame W3C propagation through the ZMQ envelope, the two are
    linked across the wire.

    Strategy: spin up one MQReceiver in a background thread and drive one
    MQSender from the test thread, both pointed at the same OTLP collector
    (jaeger). Wrap the send in a 'filterA.process' span (mimicking what
    Filter.process_frames does); on the receive side, wrap the post-recv work in
    a 'filterB.process' span parented by MQ.recv_parent_ctx (mimicking what
    Filter._process_frames_single does with the per-frame context). Query jaeger
    afterwards and assert mq.send, mq.recv, filterA.process, and filterB.process
    all share one trace ID for the frame we sent.
    """
    import json
    import threading
    import urllib.request
    import numpy as np

    from openfilter.filter_runtime.mq import MQSender, MQReceiver
    from openfilter.filter_runtime.frame import Frame
    from openfilter.observability.tracing import (
        register_hop_tracer,
        setup_tracer_provider,
    )

    resource = Resource.create({"service.name": SERVICE_NAME})
    provider = setup_tracer_provider(
        resource=resource,
        exporter_type="otlp_grpc",
        exporter_config={"endpoint": jaeger.otlp_grpc_endpoint},
    )
    tracer = provider.get_tracer("openfilter-mq-hop-test")
    register_hop_tracer(tracer)

    # IPC socket lives in the test's tmp dir so parallel runs don't collide.
    ipc_addr = f"ipc://{tmp_path}/mq-hop-test.sock"

    recv_ready = threading.Event()
    recv_done = threading.Event()
    recv_state: dict = {}

    def receiver_thread():
        # MQReceiver creates ZMQ sockets in the thread that constructs it; doing
        # that here keeps all sub/push handles on the consumer thread.
        rcv = MQReceiver(ipc_addr, mq_id="filterB-recv", tracer=tracer)
        try:
            recv_ready.set()
            # Poll for up to a few seconds for the frame; jaeger fixture has its
            # own timeout for export visibility, so we want to be patient here.
            frames = None
            for _ in range(50):
                frames = rcv.recv(timeout=200)
                if frames:
                    break
            assert frames, "receiver never got a frame"
            # Mimic Filter._process_frames_single: use the per-frame extracted
            # context as the parent for the consumer-side process span. This is
            # the load-bearing line that links filter B's process span to
            # filter A's mq.send across the wire.
            with tracer.start_as_current_span(
                "filterB.process", context=rcv.recv_parent_ctx
            ) as proc_span:
                recv_state["filterB_trace_id"] = (
                    f"{proc_span.get_span_context().trace_id:032x}"
                )
            recv_state["received"] = True
        finally:
            rcv.destroy()
            recv_done.set()

    t = threading.Thread(target=receiver_thread, daemon=True)
    t.start()
    assert recv_ready.wait(timeout=5), "receiver thread never started"

    snd = MQSender(ipc_addr, mq_id="filterA-send", tracer=tracer)
    try:
        img = np.zeros((4, 4, 3), dtype=np.uint8)
        frame = Frame(img, {"meta": {"id": "frame-cross-filter"}}, "RGB")
        # Wrap send in a producer-side process span so mq.send nests properly.
        with tracer.start_as_current_span("filterA.process") as proc_a:
            producer_trace_id = f"{proc_a.get_span_context().trace_id:032x}"
            assert snd.send({"main": frame}, timeout=5000), "send failed"
        recv_state["filterA_trace_id"] = producer_trace_id
    finally:
        # Give the receiver thread time to drain the frame before we tear down.
        recv_done.wait(timeout=10)
        snd.destroy()
        register_hop_tracer(None)

    assert recv_state.get("received"), "receiver thread did not complete"
    assert recv_state["filterA_trace_id"] == recv_state["filterB_trace_id"], (
        f"filter A and filter B did not end up in the same trace: "
        f"A={recv_state['filterA_trace_id']!r} B={recv_state['filterB_trace_id']!r} "
        f"— per-frame W3C trace context did not propagate through the ZMQ envelope"
    )

    provider.force_flush(timeout_millis=5000)
    provider.shutdown()

    # Round-trip via jaeger to confirm the spans landed there too. We don't
    # assert specific span counts (BatchSpanProcessor + jaeger ingestion ordering
    # are not deterministic enough), just that the trace exists and our service
    # contributed to it under the expected trace_id.
    services = jaeger.wait_for_trace(producer_trace_id, timeout_secs=10.0)
    assert SERVICE_NAME in services, (
        f"expected service.name={SERVICE_NAME!r} in jaeger trace {producer_trace_id}, "
        f"got {services!r}"
    )

    # And the trace should contain spans for both producer and consumer process
    # spans plus the hop spans on both legs. We fetch the raw trace JSON and
    # confirm at least mq.send, mq.recv, and the two .process spans are present.
    url = f"{jaeger.query_base_url}/api/traces/{producer_trace_id}"
    with urllib.request.urlopen(url, timeout=5) as resp:
        body = resp.read()
    parsed = json.loads(body)
    span_names = {
        s.get("operationName")
        for trace in parsed.get("data", [])
        for s in trace.get("spans", [])
    }
    expected = {"mq.send", "mq.recv", "filterA.process", "filterB.process"}
    missing = expected - span_names
    assert not missing, (
        f"jaeger trace {producer_trace_id} missing expected hop spans: {missing!r}; "
        f"saw {sorted(span_names)!r}"
    )


@pytest.mark.slow
def test_traceparent_env_is_honored(jaeger, monkeypatch):
    """Extracting TRACEPARENT env must yield spans nested under the parent.

    This is the load-bearing path for the api -> agent -> controller ->
    filter trace chain: the controller writes TRACEPARENT onto filter pods
    from a CR annotation, and openfilter must consume it so spans land on
    the existing distributed trace instead of starting a new one.
    """
    from openfilter.observability.tracing import extract_parent_context

    parent_trace_id = "0af7651916cd43dd8448eb211c80319c"
    parent_span_id = "b7ad6b7169203331"
    monkeypatch.setenv(
        "TRACEPARENT", f"00-{parent_trace_id}-{parent_span_id}-01"
    )

    resource = Resource.create({"service.name": SERVICE_NAME})
    provider = setup_tracer_provider(
        resource=resource,
        exporter_type="otlp_grpc",
        exporter_config={"endpoint": jaeger.otlp_grpc_endpoint},
    )
    tracer = provider.get_tracer("openfilter-integration-test")
    parent_ctx = extract_parent_context()
    assert parent_ctx is not None, "extract_parent_context returned None with TRACEPARENT set"

    with tracer.start_as_current_span("child.of.injected", context=parent_ctx) as span:
        sc = span.get_span_context()
        emitted_trace_id = f"{sc.trace_id:032x}"

    provider.force_flush(timeout_millis=5000)
    provider.shutdown()

    assert emitted_trace_id == parent_trace_id, (
        f"expected emitted trace_id to match injected parent {parent_trace_id}, "
        f"got {emitted_trace_id}"
    )

    # And jaeger should have our service under THAT trace_id too.
    services = jaeger.wait_for_trace(parent_trace_id, timeout_secs=10.0)
    assert SERVICE_NAME in services, (
        f"expected service.name={SERVICE_NAME!r} in jaeger trace {parent_trace_id}, "
        f"got {services!r}"
    )
