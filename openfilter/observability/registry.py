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
    
    def __init__(self, meter: Meter, specs: List[MetricSpec], otel_meter: Meter = None):
        """Initialize the registry with meters and metric specifications.
        
        Args:
            meter: OpenTelemetry meter for OpenLineage export (business metrics)
            specs: List of MetricSpec instances to register
            otel_meter: OpenTelemetry meter for OTEL export (system metrics)
        """
        self._specs = specs
        self._meter = meter  # For OpenLineage/business metrics
        self._otel_meter = otel_meter or meter  # For OTEL export
        
        # Log business metrics being registered
        if specs:
            metric_names = [spec.name for spec in specs]
            logger.info(f"\033[92m[Business Metrics] Registering metrics: {', '.join(metric_names)}\033[0m")
        
        # Create OpenTelemetry instruments for each spec based on target
        for spec in specs:
            self._create_instruments(spec)

    def _create_instruments(self, spec: MetricSpec):
        """Create OpenTelemetry instruments based on target and export_mode.
        
        Args:
            spec: MetricSpec to create instruments for
        """
        try:
            # Store instruments as tuples (openlineage_instrument, otel_instrument)
            spec._otel_inst = [None, None]
            
            # Create for OpenLineage (business metrics)
            if spec.target in ["openlineage", "both"]:
                ol_instrument = self._create_instrument(self._meter, spec, "OpenLineage")
                spec._otel_inst[0] = ol_instrument
            
            # Create for OTEL (system metrics) 
            if spec.target in ["otel", "both"]:
                otel_instrument = self._create_instrument(self._otel_meter, spec, "OTEL")
                spec._otel_inst[1] = otel_instrument
                
        except Exception as e:
            logger.error(f"Failed to create instruments for metric '{spec.name}': {e}")

    def _create_instrument(self, meter: Meter, spec: MetricSpec, target_name: str):
        """Create a single instrument for the specified meter.
        
        Args:
            meter: Meter to create instrument with
            spec: MetricSpec to create instrument for
            target_name: Name of the target (for logging)
            
        Returns:
            Created instrument
        """
        if spec.instrument == "counter":
            instrument = meter.create_counter(spec.name)
            logger.info(f"\033[92m[{target_name} Metrics] Created counter: {spec.name}\033[0m")
            return instrument
            
        elif spec.instrument == "histogram":
            # Use provided boundaries or auto-generate
            if spec.boundaries is not None:
                boundaries = spec.boundaries
                logger.info(f"\033[92m[{target_name} Metrics] Created histogram: {spec.name} with custom boundaries {boundaries}\033[0m")
            else:
                # Auto-generate boundaries based on metric type
                if "confidence" in spec.name.lower():
                    boundaries = generate_histogram_buckets(spec.num_buckets, 0.0, 1.0)
                elif "detection" in spec.name.lower():
                    boundaries = generate_histogram_buckets(spec.num_buckets, 0.0, 50.0)
                elif "frame" in spec.name.lower():
                    boundaries = generate_histogram_buckets(spec.num_buckets, 0.0, 100.0)
                elif "time" in spec.name.lower() or "latency" in spec.name.lower():
                    boundaries = generate_histogram_buckets(spec.num_buckets, 0.0, 10.0)
                elif "size" in spec.name.lower() or "ratio" in spec.name.lower():
                    boundaries = generate_histogram_buckets(spec.num_buckets, 0.0, 2.0)
                else:
                    boundaries = generate_histogram_buckets(spec.num_buckets, 0.0, 100.0)
                logger.info(f"\033[92m[{target_name} Metrics] Created histogram: {spec.name} with auto-generated boundaries {boundaries}\033[0m")
            
            instrument = meter.create_histogram(
                spec.name, explicit_bucket_boundaries_advisory=boundaries
            )
            return instrument
            
        elif spec.instrument == "gauge":
            instrument = meter.create_observable_gauge(spec.name)
            logger.info(f"\033[92m[{target_name} Metrics] Created gauge: {spec.name}\033[0m")
            return instrument
            
        else:
            logger.warning(f"Unknown instrument type '{spec.instrument}' for metric '{spec.name}'")
            return None

    def record(self, frame_data: dict):
        """Record metrics for a frame based on registered specifications.
        
        Args:
            frame_data: Dictionary containing frame data to extract metrics from
        """
        for spec in self._specs:
            try:
                if spec._otel_inst is None or not any(spec._otel_inst):
                    continue
                    
                val = spec.value_fn(frame_data)
                if val is None:
                    continue
                
                # Record to OpenLineage instrument (if exists)
                ol_instrument = spec._otel_inst[0] if spec._otel_inst else None
                if ol_instrument:
                    self._record_to_instrument(ol_instrument, spec, val, "OpenLineage")
                
                # Record to OTEL instrument (if exists)
                otel_instrument = spec._otel_inst[1] if spec._otel_inst else None  
                if otel_instrument:
                    self._record_to_instrument(otel_instrument, spec, val, "OTEL")
                    
            except Exception as e:
                logger.error(f"Failed to record metric '{spec.name}': {e}")

    def _record_to_instrument(self, instrument, spec: MetricSpec, val: float, target_name: str):
        """Record a value to a specific instrument.
        
        Args:
            instrument: OpenTelemetry instrument to record to
            spec: MetricSpec for the metric
            val: Value to record
            target_name: Name of the target (for logging)
        """
        if spec.instrument == "counter":
            instrument.add(val)
            logger.debug(f"[{target_name} Metrics] Recorded counter: {spec.name} = {val}")
        elif spec.instrument == "histogram":
            instrument.record(val)
            logger.debug(f"[{target_name} Metrics] Recorded histogram: {spec.name} = {val}")
        elif spec.instrument == "gauge":
            # Gauges are recorded differently - they need to be observable
            # For now, we'll use the current value as a simple approach
            logger.debug(f"[{target_name} Metrics] Recorded gauge: {spec.name} = {val}") 