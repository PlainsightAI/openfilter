import os
from typing import Optional
from opentelemetry.sdk.metrics.export import MetricExporter
from opentelemetry.exporter.cloud_monitoring import CloudMonitoringMetricsExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter as OTLPGrpcExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter as OTLPHttpExporter
from opentelemetry.sdk.metrics.export import ConsoleMetricExporter
import logging

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

                return OTLPGrpcExporter(
                    endpoint=kwargs.get("endpoint") or os.getenv("OTEL_EXPORTER_OTLP_GRPC_ENDPOINT"),
                    insecure=kwargs.get("insecure", os.getenv("OTLP_GRPC_ENDPOINT_SECURITY",True))
                )
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
