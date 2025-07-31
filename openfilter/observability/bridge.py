"""
OpenTelemetry to OpenLineage bridge for safe metric export.

This module provides the OTelLineageExporter that converts OpenTelemetry metrics
into safe JSON fragments for OpenLineage heartbeat facets.
"""

import logging
import fnmatch
from typing import Optional, Set
from opentelemetry.sdk.metrics.export import MetricExporter, MetricsData
from opentelemetry.sdk.metrics.export import MetricExporterResult

from .lineage import OpenFilterLineage

logger = logging.getLogger(__name__)


class OTelLineageExporter(MetricExporter):
    """Takes the batch that OTel already aggregated and forwards
       safe metrics into OpenLineage as a heartbeat facet."""
    
    def __init__(self, lineage: OpenFilterLineage, allowlist: Optional[Set[str]] = None):
        """Initialize the exporter.
        
        Args:
            lineage: OpenFilterLineage instance for emitting heartbeats
            allowlist: Set of allowed metric names (None means allow all)
        """
        super().__init__(preferred_temporality={})
        self._lineage = lineage
        self._allow = allowlist

    def export(self, metrics: MetricsData) -> MetricExporterResult:
        """Export metrics to OpenLineage as heartbeat facets.
        
        Args:
            metrics: OpenTelemetry metrics data
            
        Returns:
            MetricExporterResult indicating success or failure
        """
        try:
            facet = {}
            
            for rm in metrics.resource_metrics:
                for sm in rm.scope_metrics:
                    for dp in sm.metrics:
                        name = dp.name
                        
                        # Check allowlist
                        if self._allow and not self._is_allowed(name):
                            continue
                            
                        if dp.data.type == "sum":
                            # Counter → single number for this export window
                            if dp.data.points and len(dp.data.points) > 0:
                                facet[name] = int(dp.data.points[0].value)
                                
                        elif dp.data.type == "histogram":
                            # Histogram → detailed bucket information
                            if dp.data.points and len(dp.data.points) > 0:
                                h = dp.data.points[0]
                                facet[f"{name}_histogram"] = {
                                    "buckets": list(h.explicit_bounds) if hasattr(h, 'explicit_bounds') else [],
                                    "counts": list(h.bucket_counts) if hasattr(h, 'bucket_counts') else [],
                                    "count": int(h.count) if hasattr(h, 'count') else 0,
                                    "sum": float(h.sum) if hasattr(h, 'sum') else 0.0,
                                }
            
            if facet:
                self._lineage.update_heartbeat_lineage(facets=facet)
                
            return MetricExporterResult.SUCCESS
            
        except Exception as e:
            logger.error(f"Failed to export metrics to OpenLineage: {e}")
            return MetricExporterResult.FAILURE

    def _is_allowed(self, metric_name: str) -> bool:
        """Check if a metric name is allowed by the allowlist.
        
        Args:
            metric_name: Name of the metric to check
            
        Returns:
            True if the metric is allowed, False otherwise
        """
        if not self._allow:
            return True
            
        # Check exact match
        if metric_name in self._allow:
            return True
            
        # Check wildcard patterns
        for pattern in self._allow:
            if fnmatch.fnmatch(metric_name, pattern):
                return True
                
        return False

    def shutdown(self) -> None:
        """Shutdown the exporter."""
        pass 