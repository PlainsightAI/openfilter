"""Tests for observability.client.build_exporter OTLP gRPC TLS inference.

This is the metrics builder the live filter runtime actually uses (via
``OpenTelemetryClient`` in ``openfilter.observability.client``). Mirrors
the assertion style of ``test_open_telemetry_exporter_factory.py``:
patch the exporter constructor in the builder's module namespace and
pin the exact ``(endpoint, insecure)`` kwargs.

The exporter import is lazy (inside the ``elif exporter_type == "otlp"``
branch), so we patch the class on its source module rather than on a
re-export in ``client``.
"""

import unittest
from unittest.mock import patch

from openfilter.observability.client import build_exporter


EXPORTER_PATH = (
    "opentelemetry.exporter.otlp.proto.grpc.metric_exporter.OTLPMetricExporter"
)


class TestBuildExporterOtlpInsecureInference(unittest.TestCase):
    def test_http_endpoint_infers_insecure(self):
        with patch.dict("os.environ", {}, clear=True), patch(EXPORTER_PATH) as mock_exporter:
            build_exporter("otlp", endpoint="http://localhost:4317")
        mock_exporter.assert_called_once_with(
            endpoint="http://localhost:4317", insecure=True
        )

    def test_https_endpoint_infers_tls(self):
        with patch.dict("os.environ", {}, clear=True), patch(EXPORTER_PATH) as mock_exporter:
            build_exporter("otlp", endpoint="https://collector.example.com:4317")
        mock_exporter.assert_called_once_with(
            endpoint="https://collector.example.com:4317", insecure=False
        )

    def test_bare_host_endpoint_infers_tls(self):
        # Regression: matches the production bug where filter pods got
        # TELEMETRY_EXPORTER_OTLP_ENDPOINT=otel-collector.monitoring.svc...:4317
        # and OTLPMetricExporter defaulted to TLS against a plaintext
        # collector. With the inference in place a bare host:port still
        # picks TLS by default — operators against a plaintext collector
        # must opt back in with insecure=True.
        with patch.dict("os.environ", {}, clear=True), patch(EXPORTER_PATH) as mock_exporter:
            build_exporter("otlp", endpoint="collector:4317")
        mock_exporter.assert_called_once_with(
            endpoint="collector:4317", insecure=False
        )

    def test_explicit_insecure_overrides_inference(self):
        with patch.dict("os.environ", {}, clear=True), patch(EXPORTER_PATH) as mock_exporter:
            build_exporter("otlp", endpoint="collector:4317", insecure=True)
        mock_exporter.assert_called_once_with(
            endpoint="collector:4317", insecure=True
        )

    def test_unset_endpoint_falls_back_to_localhost_plaintext(self):
        # No kwarg, no env: localhost fallback keeps `docker run
        # otel/opentelemetry-collector` working unconfigured.
        with patch.dict("os.environ", {}, clear=True), patch(EXPORTER_PATH) as mock_exporter:
            build_exporter("otlp")
        mock_exporter.assert_called_once_with(
            endpoint="http://localhost:4317", insecure=True
        )

    def test_telemetry_exporter_otlp_endpoint_env_used(self):
        # The Plainsight-convention env var is the one the live deployment
        # sets in the filter pod env (see the filter Deployment spec
        # emitted by the openfilter-pipelines-controller).
        env = {"TELEMETRY_EXPORTER_OTLP_ENDPOINT": "https://plainsight.example:4317"}
        with patch.dict("os.environ", env, clear=True), patch(EXPORTER_PATH) as mock_exporter:
            build_exporter("otlp")
        mock_exporter.assert_called_once_with(
            endpoint="https://plainsight.example:4317", insecure=False
        )


if __name__ == "__main__":
    unittest.main()
