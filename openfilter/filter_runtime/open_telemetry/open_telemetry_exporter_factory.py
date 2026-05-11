import os
from typing import Optional
from opentelemetry.sdk.metrics.export import MetricExporter
from opentelemetry.exporter.cloud_monitoring import CloudMonitoringMetricsExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter as OTLPGrpcExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter as OTLPHttpExporter
from opentelemetry.sdk.metrics.export import ConsoleMetricExporter
import logging

from openfilter.observability._otlp import infer_otlp_insecure

class ExporterFactory:
    @staticmethod
    def build(exporter_type: str, **kwargs) -> MetricExporter:

        exporter_type = exporter_type.lower()

        if exporter_type == "gcm":
            return CloudMonitoringMetricsExporter(
                project_id=kwargs.get("project_id") or os.getenv("PROJECT_ID")
            )

        elif exporter_type == "otlp_grpc":
            try:
                # Mirror the tracing factory's localhost fallback so an unset
                # endpoint stays plaintext-against-localhost rather than
                # falling through to the SDK's TLS default and breaking local
                # `docker run otel/opentelemetry-collector` setups.
                endpoint = (
                    kwargs.get("endpoint")
                    or os.getenv("OTEL_EXPORTER_OTLP_GRPC_ENDPOINT")
                    or "http://localhost:4317"
                )
                # Infer TLS from the endpoint scheme (http://=plaintext,
                # https://=TLS, bare host:port=TLS). Explicit insecure=
                # always wins. Replaces the prior OTLP_GRPC_ENDPOINT_SECURITY
                # env-var lookup, which never parsed strings to bool and so
                # was effectively always insecure=True.
                insecure = kwargs.get("insecure")
                if insecure is None:
                    insecure = infer_otlp_insecure(endpoint)
                return OTLPGrpcExporter(endpoint=endpoint, insecure=insecure)
            except Exception as e:
                logging.error(f"Failed to set OTLP_GRPC exporter {e}")

        elif exporter_type == "otlp_http":
            try:
                return OTLPHttpExporter(
                    endpoint=kwargs.get("endpoint") or os.getenv("OTEL_EXPORTER_OTLP_HTTP_ENDPOINT"),
                    headers=kwargs.get("headers") or {}
                )
            except Exception as e:
                logging.error(f"Failed to set OTLP_HTTP exporter {e}")

        elif exporter_type == "console":
            try:
                return ConsoleMetricExporter()
            except Exception as e:
                logging.error("Failed to set Console exporter {e}")

        else:
            raise ValueError(f"Unsupported exporter type: {exporter_type}")
