
from collections import defaultdict
import threading
import time
from typing import Optional
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


from openfilter.filter_runtime.open_telemetry.open_telemetry_exporter_factory import ExporterFactory

DEFAULT_EXPORTER_TYPE = "console"
DEFAULT_EXPORT_INTERVAL_MS = 60000
DEFAULT_PROJECT_ID = "plainsightai-dev"
DEFAULT_TELEMETRY_ENABLED = False



class OpenTelemetryClient:
    def __init__(
        self,
        service_name: str = "openfilter",
        namespace: str = "telemetry",
        instance_id: Optional[str] = None,
        setup_metrics: Optional[dict] = None,
        exporter_type: str = os.getenv("TELEMETRY_EXPORTER_TYPE", DEFAULT_EXPORTER_TYPE),
        export_interval_millis: int = DEFAULT_EXPORT_INTERVAL_MS,
        exporter_config: Optional[dict] = None,
        enabled: bool = os.getenv("TELEMETRY_EXPORTER_ENABLED", DEFAULT_TELEMETRY_ENABLED),  
        project_id: str | None = DEFAULT_PROJECT_ID
    ):

        self.enabled = enabled
        self.instance_id = instance_id
        self.setup_metrics = setup_metrics or {}
        exporter_config = exporter_config or {}

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

                exporter = ExporterFactory.build(exporter_type, **exporter_config)

                metric_reader = PeriodicExportingMetricReader(
                    exporter=exporter, export_interval_millis=export_interval_millis
                )

                self.provider = MeterProvider(
                    resource=resource, metric_readers=[metric_reader]
                )
                set_meter_provider(self.provider)
                self.meter = get_meter(service_name)
            except Exception as e:
                logging.exception(f"Failed to initialize telemetry exporter '{exporter_type}': {e}")
                logging.warning("Telemetry will be disabled due to initialization failure.")
                self.enabled = False
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
        
        if not self.enabled:
            return

        try:
            with self._lock:
                for name, value in metrics_dict.items():
                    if not isinstance(value, (int, float)):
                        continue

                    metric_key = f"{filter_name}_{name}"
                    self._values[metric_key] = value
                    self._metric_groups[name].append(metric_key)

                    # Cria o gauge observável na primeira vez
                    if metric_key not in self._metrics:
                        attributes = {
                            **self.setup_metrics,
                            "filter_name": filter_name,
                            "metric_name": name,
                            "timestamp": datetime.utcnow().isoformat() + "Z",
                        }

                        def make_callback(key, attrs):
                            return lambda options: [
                                Observation(self._values.get(key, 0.0), attributes=attrs)
                            ]

                        instrument = self.meter.create_observable_gauge(
                            name=metric_key,
                            callbacks=[make_callback(metric_key, attributes)],
                            description=f"Metric for {filter_name}.{name}",
                        )
                        self._metrics[metric_key] = instrument
        except Exception as e:
          logging.error("error with telemetry {e}")
