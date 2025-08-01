"""
MetricSpec dataclass for declarative metric definitions.

This module provides the MetricSpec class that allows filters to declare
safe metrics without hard-coding metric logic in the base Filter class.
"""

from dataclasses import dataclass, field
from typing import Callable, List, Optional, Any


@dataclass
class MetricSpec:
    """Declarative description of one safe metric."""
    name: str                                                               # 'frames_with_plate'
    instrument: str                                                         # 'counter' | 'histogram'
    value_fn: Callable[[dict], Optional[int | float]]                       # given frame.data ➜ value
    boundaries: Optional[List[float]] = None  # for histogram

    # runtime fields – filled in by TelemetryRegistry
    _otel_inst: Optional[Any] = field(default=None, init=False) 