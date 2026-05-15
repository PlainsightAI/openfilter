"""Tests for the metrics ExporterFactory's OTLP gRPC TLS inference.

Mirrors the cases in ``test_tracing.py`` against the metrics path, since
that path also dropped the broken ``OTLP_GRPC_ENDPOINT_SECURITY`` env-var
lookup and now defers to ``infer_otlp_insecure``.

Each test patches the exporter constructor in the factory module rather
than relying on ``assertIsInstance`` — the exporter class is the same
``OTLPGrpcExporter`` regardless of which env var wins, so an instance
check alone cannot tell precedence apart.
"""

import unittest
from unittest.mock import patch

from openfilter.filter_runtime.open_telemetry.open_telemetry_exporter_factory import (
    ExporterFactory,
)


EXPORTER_PATH = (
    "openfilter.filter_runtime.open_telemetry."
    "open_telemetry_exporter_factory.OTLPGrpcExporter"
)


class TestOtlpGrpcExporterFactory(unittest.TestCase):
    def test_http_endpoint_infers_insecure(self):
        with patch.dict("os.environ", {}, clear=True), patch(EXPORTER_PATH) as mock_exporter:
            ExporterFactory.build("otlp_grpc", endpoint="http://localhost:4317")
        mock_exporter.assert_called_once_with(
            endpoint="http://localhost:4317", insecure=True
        )

    def test_https_endpoint_infers_tls(self):
        # An https:// endpoint must infer insecure=False so we don't silently
        # send plaintext over a link the operator declared TLS.
        with patch.dict("os.environ", {}, clear=True), patch(EXPORTER_PATH) as mock_exporter:
            ExporterFactory.build(
                "otlp_grpc", endpoint="https://collector.example.com:4317"
            )
        mock_exporter.assert_called_once_with(
            endpoint="https://collector.example.com:4317", insecure=False
        )

    def test_explicit_insecure_overrides_inference(self):
        # Operators with a plaintext collector behind bare host:port must
        # still be able to opt in with insecure=True even though the bare
        # form infers insecure=False on its own.
        with patch.dict("os.environ", {}, clear=True), patch(EXPORTER_PATH) as mock_exporter:
            ExporterFactory.build(
                "otlp_grpc", endpoint="collector:4317", insecure=True
            )
        mock_exporter.assert_called_once_with(
            endpoint="collector:4317", insecure=True
        )

    def test_unset_endpoint_falls_back_to_localhost_plaintext(self):
        # Regression: with no kwarg and no env var, the factory must NOT let
        # endpoint=None reach the SDK (which would then default to TLS against
        # localhost:4317 and break `docker run otel/opentelemetry-collector`).
        # The localhost fallback keeps local-dev plaintext working.
        with patch.dict("os.environ", {}, clear=True), patch(EXPORTER_PATH) as mock_exporter:
            ExporterFactory.build("otlp_grpc")
        mock_exporter.assert_called_once_with(
            endpoint="http://localhost:4317", insecure=True
        )

    def test_telemetry_exporter_otlp_endpoint_takes_precedence(self):
        # The Plainsight-convention env var must win over the standard OTel
        # one and over the legacy GRPC-specific one, matching the precedence
        # in build_span_exporter so an operator setting a single
        # TELEMETRY_EXPORTER_OTLP_ENDPOINT gets both traces *and* metrics.
        env = {
            "TELEMETRY_EXPORTER_OTLP_ENDPOINT": "https://plainsight.example:4317",
            "OTEL_EXPORTER_OTLP_ENDPOINT": "https://otel.example:4317",
            "OTEL_EXPORTER_OTLP_GRPC_ENDPOINT": "https://grpc.example:4317",
        }
        with patch.dict("os.environ", env, clear=True), patch(EXPORTER_PATH) as mock_exporter:
            ExporterFactory.build("otlp_grpc")
        mock_exporter.assert_called_once_with(
            endpoint="https://plainsight.example:4317", insecure=False
        )

    def test_otel_exporter_otlp_endpoint_used_when_telemetry_var_unset(self):
        # When the Plainsight-convention var is unset, the standard OTel
        # spec var should take precedence over the legacy GRPC-specific one.
        env = {
            "OTEL_EXPORTER_OTLP_ENDPOINT": "https://otel.example:4317",
            "OTEL_EXPORTER_OTLP_GRPC_ENDPOINT": "https://grpc.example:4317",
        }
        with patch.dict("os.environ", env, clear=True), patch(EXPORTER_PATH) as mock_exporter:
            ExporterFactory.build("otlp_grpc")
        mock_exporter.assert_called_once_with(
            endpoint="https://otel.example:4317", insecure=False
        )


if __name__ == "__main__":
    unittest.main()
