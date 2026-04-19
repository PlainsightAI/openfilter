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
