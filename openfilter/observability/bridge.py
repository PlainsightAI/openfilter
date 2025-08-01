"""
OpenTelemetry to OpenLineage bridge for safe metric export.

This module provides the OTelLineageExporter that converts OpenTelemetry metrics
into safe JSON fragments for OpenLineage heartbeat facets.
"""

import logging
import fnmatch
from typing import Optional, Set
from opentelemetry.sdk.metrics.export import MetricExporter, MetricsData, MetricExportResult

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
        
        if allowlist:
            logger.info(f"[OpenLineage Export] Allowlist configured: {list(allowlist)}")
        else:
            logger.info(f"[OpenLineage Export] No allowlist - allowing all metrics")

    def export(self, metrics: MetricsData, timeout_millis: float = 30000) -> MetricExportResult:
        """Export metrics to OpenLineage as heartbeat facets.
        
        Args:
            metrics: OpenTelemetry metrics data
            timeout_millis: Timeout in milliseconds (ignored for this exporter)
            
        Returns:
            MetricExportResult indicating success or failure
        """
        try:
            facet = {}
            logger.info(f"[OpenLineage Export] Processing {len(metrics.resource_metrics)} resource metrics")
            
            for rm in metrics.resource_metrics:
                for sm in rm.scope_metrics:
                    logger.info(f"[OpenLineage Export] Processing scope: {sm.scope.name} with {len(sm.metrics)} metrics")
                    for dp in sm.metrics:
                        name = dp.name
                        logger.info(f"[OpenLineage Export] Processing metric: {name}")
                        
                        # Check allowlist
                        if self._allow and not self._is_allowed(name):
                            logger.info(f"[OpenLineage Export] Skipping {name} - not in allowlist")
                            continue
                            
                        # Check the type of metric data using isinstance
                        if hasattr(dp.data, 'data_points') and dp.data.data_points:
                            point = dp.data.data_points[0]
                            
                            # Handle Sum (Counter) metrics
                            if hasattr(dp.data, 'is_monotonic') and dp.data.is_monotonic:
                                facet[name] = int(point.value)
                                logger.info(f"[OpenLineage Export] Added counter: {name} = {int(point.value)}")
                                
                            # Handle Histogram metrics
                            elif hasattr(point, 'bucket_counts') and hasattr(point, 'explicit_bounds'):
                                facet[f"{name}_histogram"] = {
                                    "buckets": list(point.explicit_bounds) if hasattr(point, 'explicit_bounds') else [],
                                    "counts": list(point.bucket_counts) if hasattr(point, 'bucket_counts') else [],
                                    "count": int(point.count) if hasattr(point, 'count') else 0,
                                    "sum": float(point.sum) if hasattr(point, 'sum') else 0.0,
                                }
                                logger.info(f"[OpenLineage Export] Added histogram: {name}_histogram = {facet[f'{name}_histogram']}")
                                
                            # Handle Gauge metrics (non-monotonic)
                            elif hasattr(point, 'value'):
                                facet[name] = float(point.value)
                                logger.info(f"[OpenLineage Export] Added gauge: {name} = {float(point.value)}")
            
            if facet:
                logger.info(f"[OpenLineage Export] Sending metrics: {list(facet.keys())}")
                self._lineage.update_heartbeat_lineage(facets=facet)
                
            return MetricExportResult.SUCCESS
            
        except Exception as e:
            logger.error(f"\033[91mFailed to export metrics to OpenLineage: {e}\033[0m")
            return MetricExportResult.FAILURE

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
    
    def force_flush(self, timeout_millis: float = 30000) -> MetricExportResult:
        """Force flush any pending metrics.
        as per https://opentelemetry.io/docs/specs/otel/metrics/sdk/#forceflush
        
        Args:
            timeout_millis: Timeout in milliseconds
            
        Returns:
            MetricExportResult indicating success or failure
        """
        try:
            # Trigger a heartbeat to ensure metrics are sent
            if hasattr(self._lineage, 'update_heartbeat_lineage'):
                self._lineage.update_heartbeat_lineage()
            return MetricExportResult.SUCCESS
        except Exception as e:
            logger.error(f"\033[93mFailed to force flush metrics: {e}\033[0m")
            return MetricExportResult.FAILURE

    def shutdown(self, timeout: float = 30000) -> None:
        """Shutdown the exporter.
        
        Args:
            timeout: Timeout in seconds (ignored for this exporter)
        """
        pass 