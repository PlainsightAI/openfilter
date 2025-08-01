"""
OpenTelemetry client for OpenFilter observability.

This module provides the OpenTelemetryClient that manages metric collection
and export to various backends including OpenLineage.
"""

from collections import defaultdict
import threading
import time
from typing import Optional, Any
from datetime import datetime
import os
import logging

from opentelemetry import metrics
from opentelemetry.sdk.resources import (
    Resource,
    SERVICE_NAME,
    SERVICE_NAMESPACE,
    SERVICE_INSTANCE_ID, 
)
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.metrics import Observation, set_meter_provider, get_meter

from distutils.util import strtobool
from .bridge import OTelLineageExporter
from .config import read_allowlist

# Simple exporter factory for basic exporters
def build_exporter(exporter_type: str, **config):
    """Build a basic exporter for the demo."""
    if exporter_type == "console":
        from opentelemetry.sdk.metrics.export import ConsoleMetricExporter
        return ConsoleMetricExporter()
    elif exporter_type == "silent":
        # Silent exporter that doesn't print to console
        from opentelemetry.sdk.metrics.export import MetricExporter, MetricExportResult, MetricsData
        class SilentMetricExporter(MetricExporter):
            def export(self, metrics: MetricsData, timeout_millis: float = 30000) -> MetricExportResult:
                # Do nothing - silent export
                return MetricExportResult.SUCCESS
            def force_flush(self, timeout_millis: float = 30000) -> MetricExportResult:
                return MetricExportResult.SUCCESS
            def shutdown(self, timeout: float = 30000) -> None:
                pass
        return SilentMetricExporter()
    
    elif exporter_type == "otlp":
        from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
        endpoint = config.get("endpoint", "http://localhost:4317")
        return OTLPMetricExporter(endpoint=endpoint)
    else:
        from opentelemetry.sdk.metrics.export import ConsoleMetricExporter
        return ConsoleMetricExporter()

DEFAULT_EXPORTER_TYPE = "silent"
DEFAULT_EXPORT_INTERVAL_MS = 30000
DEFAULT_TELEMETRY_ENABLED = False


class OpenTelemetryClient:
    """OpenTelemetry client for OpenFilter metric collection and export."""
    
    def __init__(
        self,
        service_name: str = "openfilter",
        namespace: str = "telemetry",
        instance_id: Optional[str] = None,
        setup_metrics: Optional[dict] = None,
        exporter_type: str = os.getenv("TELEMETRY_EXPORTER_TYPE", DEFAULT_EXPORTER_TYPE),
        export_interval_millis: int = None,
        exporter_config: Optional[dict] = None,
        enabled: bool = None,  
        project_id: str | None = os.getenv("PROJECT_ID", None),
        lineage_emitter: Optional[Any] = None
    ):
        """Initialize the OpenTelemetry client.
        
        Args:
            service_name: Name of the service
            namespace: Namespace for the service
            instance_id: Unique instance identifier
            setup_metrics: Initial metrics to set up
            exporter_type: Type of exporter to use
            export_interval_millis: Export interval in milliseconds
            exporter_config: Configuration for the exporter
            enabled: Whether telemetry is enabled
            project_id: Cloud project ID
            lineage_emitter: OpenLineage emitter for bridge export
        """
        enabled_env = os.getenv("TELEMETRY_EXPORTER_ENABLED")
        if enabled is not None:
            self.enabled = enabled
        elif enabled_env is not None:
            try:
                self.enabled = bool(strtobool(enabled_env))
            except ValueError:
                self.enabled = DEFAULT_TELEMETRY_ENABLED
        else:
            self.enabled = DEFAULT_TELEMETRY_ENABLED

        self.instance_id = instance_id
        self.setup_metrics = setup_metrics or {}
        exporter_config = exporter_config or {}

        self.export_interval_millis = max(
            int(os.getenv("EXPORT_INTERVAL", 0)) if os.getenv("EXPORT_INTERVAL") else export_interval_millis or 0,
            DEFAULT_EXPORT_INTERVAL_MS
        )

        if self.enabled:
            try:
                resource = Resource.create(
                    {
                        SERVICE_NAME: service_name,
                        SERVICE_NAMESPACE: namespace,
                        SERVICE_INSTANCE_ID: self.instance_id,
                        "cloud.account.id": project_id,
                        "cloud.resource_type": "global",
                    }
                )

                # Build the primary exporter for system metrics (to OpenTelemetry)
                primary_exporter = build_exporter(exporter_type, **exporter_config)
                
                # Create metric readers list
                metric_readers = [
                    PeriodicExportingMetricReader(
                        exporter=primary_exporter, 
                        export_interval_millis=self.export_interval_millis
                    )
                ]
                
                # Create the lineage bridge exporter for business metrics (to OpenLineage only)
                if lineage_emitter:
                    try:
                        from openfilter.observability.bridge import OTelLineageExporter
                        from openfilter.observability.config import read_allowlist
                        
                        allowlist = read_allowlist()
                        lineage_exporter = OTelLineageExporter(lineage_emitter, allowlist=allowlist)
                        
                        lineage_reader = PeriodicExportingMetricReader(
                            exporter=lineage_exporter, 
                            export_interval_millis=self.export_interval_millis
                        )
                        metric_readers.append(lineage_reader)
                        logging.info("OpenLineage bridge enabled - business metrics will be exported to OpenLineage")
                    except ImportError:
                        logging.warning("OpenLineage bridge not available - business metrics will not be exported")
                    except Exception as e:
                        logging.error(f"\033[91mFailed to initialize OpenLineage bridge: {e}\033[0m")

                # Create single provider with all metric readers
                self.provider = MeterProvider(
                    resource=resource, metric_readers=metric_readers
                )
                set_meter_provider(self.provider)
                self.meter = get_meter(service_name)
                
                # Create business meter using the same provider but with different scope
                if lineage_emitter and 'lineage_exporter' in locals():
                    try:
                        self.business_meter = get_meter(f"{service_name}_business")
                        logging.info("Business metrics meter created - metrics will only go to OpenLineage")
                    except Exception as e:
                        logging.error(f"Failed to create business metrics meter: {e}")
                        self.business_meter = None
                else:
                    self.business_meter = None
            except Exception as e:
                logging.error(f"Error setting Open Telemetry: {e}")
        else:
            self.provider = None
            self.meter = None
            logging.info("telemetry is disabled")

        self._lock = threading.Lock()
        self._values: dict[str, float] = {}
        self._metrics: dict[str, object] = {}
        self._metric_groups: defaultdict[str, list[str]] = defaultdict(list)
        self._last_emit: dict[str, float] = {}

        self._create_aggregate_metric_callback()

    def _create_aggregate_metric_callback(self):
        """Create the aggregate metric callback for observable gauges."""
        if not self.enabled:
            return

        def aggregate_callback(options):
            now = time.time()
            observations = []

            with self._lock:
                grouped: defaultdict[str, list[float]] = defaultdict(list)

                for metric_key, value in self._values.items():
                    base_name = metric_key.split("_", 1)[-1]
                    grouped[base_name].append(value)

                for base_name, values in grouped.items():
                    # send one point per second
                    if now - self._last_emit.get(base_name, 0) < 60:
                        continue
                    self._last_emit[base_name] = now

                    avg = sum(values) / len(values)
                    attributes = {
                        "aggregation": "avg",
                        "metric": base_name,
                        "pipeline_id": self.setup_metrics.get("pipeline_id"),
                        "device_id_name": self.setup_metrics.get("device_id_name"),
                        "timestamp": datetime.utcnow().isoformat() + "Z",
                    }
                    observations.append(Observation(avg, attributes=attributes))

            return observations

        self.meter.create_observable_gauge(
            name="aggregated_metrics",
            callbacks=[aggregate_callback],
            description="Aggregated metrics across all filters in the pipeline",
        )

    def update_metrics(self, metrics_dict: dict[str, float], filter_name: str):
        """Update metrics for a specific filter.
        
        This method sends raw system metrics directly to OpenTelemetry without aggregation.
        The OTel SDK will handle aggregation and the OTelLineageExporter bridge will
        send aggregated metrics to OpenLineage.
        
        Args:
            metrics_dict: Dictionary of metric names and values
            filter_name: Name of the filter
        """
        if not self.enabled:
            return
        
        try:
            with self._lock:
                for name, value in metrics_dict.items():
                    if not isinstance(value, (int, float)):
                        continue

                    metric_key = f"{filter_name}_{name}"
                    
                    # Define attributes for this metric
                    attributes = {
                        **self.setup_metrics,
                        "filter_name": filter_name,
                        "metric_name": name,
                    }
                    
                    # Create instrument if it doesn't exist
                    if metric_key not in self._metrics:
                        # Store current value for observable gauges
                        self._values[metric_key] = value
                        
                        # Use counter for cumulative metrics, gauge for current values
                        if name in ['fps', 'cpu', 'mem', 'lat_in', 'lat_out']:
                            # Use gauge for current values
                            def make_gauge_callback(key):
                                return lambda options: [
                                    Observation(self._values.get(key, 0.0), attributes=attributes)
                                ]
                            
                            instrument = self.meter.create_observable_gauge(
                                name=metric_key,
                                callbacks=[make_gauge_callback(metric_key)],
                                description=f"Current value for {filter_name}.{name}",
                            )
                            logging.info(f"\033[92m[System Metrics] Created gauge: {metric_key} = {value}\033[0m")
                        else:
                            # Use counter for cumulative metrics
                            instrument = self.meter.create_counter(
                                name=metric_key,
                                description=f"Counter for {filter_name}.{name}",
                            )
                            logging.info(f"\033[92m[System Metrics] Created counter: {metric_key} = {value}\033[0m")
                        
                        self._metrics[metric_key] = instrument
                    
                    # Record the metric value directly
                    instrument = self._metrics[metric_key]
                    if hasattr(instrument, 'add'):
                        # Counter - add the value
                        instrument.add(value, attributes=attributes)
                    else:
                        # Gauge - update the stored value for callback
                        self._values[metric_key] = value
                        
        except Exception as e:
            logging.error(f"Error updating metrics: {e}") 