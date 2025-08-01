"""
TelemetryRegistry for managing metric recording.

This module provides the TelemetryRegistry class that handles the recording
of metrics based on MetricSpec declarations.
"""

import logging
from typing import List
from opentelemetry.metrics import Meter

from .specs import MetricSpec

logger = logging.getLogger(__name__)


class TelemetryRegistry:
    """Registry for managing metric recording based on MetricSpec declarations."""
    
    def __init__(self, meter: Meter, specs: List[MetricSpec]):
        """Initialize the registry with a meter and metric specifications.
        
        Args:
            meter: OpenTelemetry meter for creating instruments
            specs: List of MetricSpec instances to register
        """
        self._specs = specs
        self._meter = meter
        
        # Log business metrics being registered
        if specs:
            metric_names = [spec.name for spec in specs]
            logger.info(f"\033[92m[Business Metrics] Registering metrics: {', '.join(metric_names)}\033[0m")
        
        # Create OpenTelemetry instruments for each spec
        for spec in specs:
            try:
                if spec.instrument == "counter":
                    spec._otel_inst = meter.create_counter(spec.name)
                    logger.info(f"\033[92m[Business Metrics] Created counter: {spec.name}\033[0m")
                elif spec.instrument == "histogram":
                    spec._otel_inst = meter.create_histogram(
                        spec.name, explicit_bucket_boundaries_advisory=spec.boundaries or [0, 1, 2, 5, 10]
                    )
                    logger.info(f"\033[92m[Business Metrics] Created histogram: {spec.name} with boundaries {spec.boundaries or [0, 1, 2, 5, 10]}\033[0m")
                else:
                    logger.warning(f"Unknown instrument type '{spec.instrument}' for metric '{spec.name}'")
            except Exception as e:
                logger.error(f"Failed to create instrument for metric '{spec.name}': {e}")

    def record(self, frame_data: dict):
        """Record metrics for a frame based on registered specifications.
        
        Args:
            frame_data: Dictionary containing frame data to extract metrics from
        """
        for spec in self._specs:
            try:
                if spec._otel_inst is None:
                    continue
                    
                val = spec.value_fn(frame_data)
                if val is None:
                    continue
                    
                if spec.instrument == "counter":
                    spec._otel_inst.add(val)
                    logger.debug(f"[Business Metrics] Recorded counter: {spec.name} = {val}")
                elif spec.instrument == "histogram":
                    spec._otel_inst.record(val)
                    logger.debug(f"[Business Metrics] Recorded histogram: {spec.name} = {val}")
                    
            except Exception as e:
                logger.error(f"Failed to record metric '{spec.name}': {e}") 