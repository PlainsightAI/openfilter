"""
TelemetryRegistry for managing metric recording.

This module provides the TelemetryRegistry class that handles the recording
of metrics based on MetricSpec declarations.
"""

import logging
import math
from typing import List
from opentelemetry.metrics import Meter

from .specs import MetricSpec

logger = logging.getLogger(__name__)


def generate_histogram_buckets(num_buckets: int, min_val: float = 0.0, max_val: float = 100.0) -> List[float]:
    """Generate automatic histogram bucket boundaries.
    
    Args:
        num_buckets: Number of buckets to generate
        min_val: Minimum value for the first bucket
        max_val: Maximum value for the last bucket
        
    Returns:
        List of bucket boundaries (exclusive upper bounds)
        Note: For num_buckets buckets, we need num_buckets-1 boundaries
    """
    if num_buckets < 2:
        raise ValueError(f"Number of buckets must be at least 2, got {num_buckets}")
    
    # Use logarithmic spacing for better distribution
    if min_val <= 0:
        min_val = 0.1  # Avoid log(0)
    
    # For num_buckets buckets, we need num_buckets-1 boundaries
    # The last bucket is for values >= the last boundary
    num_boundaries = num_buckets - 1
    
    # Generate logarithmic buckets
    log_min = math.log(min_val)
    log_max = math.log(max_val)
    log_step = (log_max - log_min) / num_boundaries
    
    boundaries = []
    for i in range(num_boundaries):
        boundary = math.exp(log_min + i * log_step)
        boundaries.append(boundary)
    
    return boundaries


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
                    # Use provided boundaries or auto-generate
                    if spec.boundaries is not None:
                        boundaries = spec.boundaries
                        logger.info(f"\033[92m[Business Metrics] Created histogram: {spec.name} with custom boundaries {boundaries}\033[0m")
                    else:
                        # Auto-generate boundaries based on metric type
                        if "confidence" in spec.name.lower():
                            boundaries = generate_histogram_buckets(spec.num_buckets, 0.0, 1.0)
                        elif "detection" in spec.name.lower():
                            boundaries = generate_histogram_buckets(spec.num_buckets, 0.0, 50.0)
                        elif "frame" in spec.name.lower():
                            boundaries = generate_histogram_buckets(spec.num_buckets, 0.0, 100.0)
                        else:
                            boundaries = generate_histogram_buckets(spec.num_buckets, 0.0, 100.0)
                        logger.info(f"\033[92m[Business Metrics] Created histogram: {spec.name} with auto-generated boundaries {boundaries}\033[0m")
                    
                    spec._otel_inst = meter.create_histogram(
                        spec.name, explicit_bucket_boundaries_advisory=boundaries
                    )
                elif spec.instrument == "gauge":
                    spec._otel_inst = meter.create_observable_gauge(spec.name)
                    logger.info(f"\033[92m[Business Metrics] Created gauge: {spec.name}\033[0m")
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
                elif spec.instrument == "gauge":
                    # Gauges are recorded differently - they need to be observable
                    # For now, we'll use the current value as a simple approach
                    logger.debug(f"[Business Metrics] Recorded gauge: {spec.name} = {val}")
                    
            except Exception as e:
                logger.error(f"Failed to record metric '{spec.name}': {e}") 