"""
Example License Plate Filter demonstrating the new MetricSpec system.

This filter shows how to declare safe metrics using MetricSpec without
hard-coding metric logic in the base Filter class.
"""

from openfilter.filter_runtime.filter import Filter
from openfilter.observability import MetricSpec


class LicensePlateFilter(Filter):
    """Example filter that demonstrates MetricSpec declarations.
    
    This filter declares safe metrics that will be aggregated by OpenTelemetry
    and exported to OpenLineage as heartbeat facets without any PII.
    """
    
    metric_specs = [
        # Total frames processed (always 1 per frame)
        MetricSpec(
            name="frames_processed",
            instrument="counter",
            value_fn=lambda d: 1
        ),
        
        # Frames that contain license plates
        MetricSpec(
            name="frames_with_plate",
            instrument="counter", 
            value_fn=lambda d: 1 if d.get("plates") else 0
        ),
        
        # Distribution of plates per frame
        MetricSpec(
            name="plates_per_frame",
            instrument="histogram",
            value_fn=lambda d: len(d.get("plates", [])),
            boundaries=[0, 1, 2, 5, 10]
        ),
        
        # Average confidence of detected plates
        MetricSpec(
            name="plate_confidence",
            instrument="histogram",
            value_fn=lambda d: max([p.get("confidence", 0) for p in d.get("plates", [])], default=None),
            boundaries=[0.0, 0.5, 0.7, 0.8, 0.9, 1.0]
        )
    ]
    
    def process(self, frames):
        """Process frames and add license plate detection results.
        
        This is a simplified example - in a real implementation,
        you would perform actual license plate detection here.
        """
        # Example processing - in reality this would do actual detection
        for frame in frames.values():
            if hasattr(frame, 'data'):
                # Simulate license plate detection results
                frame.data["plates"] = [
                    {"confidence": 0.85, "text": "ABC123"},
                    {"confidence": 0.92, "text": "XYZ789"}
                ]
        
        return frames 