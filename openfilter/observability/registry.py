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
        
        # Create OpenTelemetry instruments for each spec
        for spec in specs:
            try:
                if spec.instrument == "counter":
                    spec._otel_inst = meter.create_counter(spec.name)
                elif spec.instrument == "histogram":
                    spec._otel_inst = meter.create_histogram(
                        spec.name, boundaries=spec.boundaries or [0, 1, 2, 5, 10]
                    )
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
                elif spec.instrument == "histogram":
                    spec._otel_inst.record(val)
                    
            except Exception as e:
                logger.error(f"Failed to record metric '{spec.name}': {e}") 