from typing import Optional
from opentelemetry.sdk.metrics.export import MetricExporter
from opentelemetry.exporter.cloud_monitoring import CloudMonitoringMetricsExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter as OTLPGrpcExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter as OTLPHttpExporter
from opentelemetry.sdk.metrics.export import ConsoleMetricExporter


 
class ExporterFactory:
    @staticmethod
    def build(exporter_type: str, **kwargs) -> MetricExporter:
       
        exporter_type = exporter_type.lower()
        
        if exporter_type == "gcm":
            return CloudMonitoringMetricsExporter(project_id=kwargs.get("project_id"))

        elif exporter_type == "otlp_grpc":
            return OTLPGrpcExporter(
                endpoint=kwargs.get("endpoint", "http://telemetry.plainsight.run:4318/v1/metrics"),
                insecure=kwargs.get("insecure", True),
            )

        elif exporter_type == "otlp_http":
            return OTLPHttpExporter(
                endpoint=kwargs.get("endpoint", "http://telemetry.plainsight.run:4318/v1/metrics"),
                headers=kwargs.get("headers", {}),
            )

        elif exporter_type == "console":
            return ConsoleMetricExporter()

        else:
            raise ValueError(f"Unsupported exporter type: {exporter_type}")
