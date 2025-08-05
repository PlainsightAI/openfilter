"""
MetricSpec for declarative metric definitions.

This module provides the MetricSpec dataclass for defining metrics
in a declarative way.
"""

from dataclasses import dataclass
from typing import Callable, List, Optional, Union
from opentelemetry.metrics import Instrument


@dataclass
class MetricSpec:
    """Specification for a metric to be recorded.
    
    Attributes:
        name: Name of the metric
        instrument: Type of instrument ('counter', 'histogram', 'gauge')
        value_fn: Function to extract value from frame data
        boundaries: For histograms, bucket boundaries (optional - will auto-generate if None)
        num_buckets: For histograms, number of buckets to auto-generate (default: 10)
        _otel_inst: OpenTelemetry instrument instance (set by TelemetryRegistry)
    """
    name: str
    instrument: str  # 'counter', 'histogram', 'gauge'
    value_fn: Callable[[dict], Union[int, float, None]]
    boundaries: Optional[List[Union[int, float]]] = None
    num_buckets: int = 10  # For auto-generated histogram buckets
    _otel_inst: Optional[Instrument] = None
    
    def __post_init__(self):
        """Validate the metric specification."""
        if self.instrument not in ['counter', 'histogram', 'gauge']:
            raise ValueError(f"Invalid instrument type: {self.instrument}. Must be 'counter', 'histogram', or 'gauge'")
        
        if self.instrument == 'histogram' and self.boundaries is not None:
            if len(self.boundaries) < 2:
                raise ValueError(f"Histogram boundaries must have at least 2 values, got {len(self.boundaries)}")
            if not all(self.boundaries[i] < self.boundaries[i+1] for i in range(len(self.boundaries)-1)):
                raise ValueError("Histogram boundaries must be in ascending order")
        
        if self.num_buckets < 2:
            raise ValueError(f"Number of buckets must be at least 2, got {self.num_buckets}") 