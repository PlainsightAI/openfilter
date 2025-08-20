"""
OpenFilter Observability System

This package provides a unified observability system that combines:
- Declarative metric specifications
- OpenTelemetry integration
- OpenLineage export
- Safe, PII-free metric aggregation

The system ensures that only numeric, aggregated metrics are exported
to external systems, preventing any PII leakage while providing rich
observability data.
"""

from .specs import MetricSpec
from .registry import TelemetryRegistry
from .bridge import OTelLineageExporter, AllowlistFilteredExporter
from .config import read_allowlist, read_otel_config
from .client import OpenTelemetryClient
from .lineage import OpenFilterLineage

__all__ = [
    'MetricSpec',
    'TelemetryRegistry', 
    'OTelLineageExporter',
    'AllowlistFilteredExporter',
    'read_allowlist',
    'read_otel_config',
    'OpenTelemetryClient',
    'OpenFilterLineage'
] 