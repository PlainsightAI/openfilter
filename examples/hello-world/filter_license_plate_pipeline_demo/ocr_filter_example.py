"""
Example OCR Filter demonstrating the new MetricSpec system.

This filter shows how to declare safe metrics for OCR processing
without hard-coding metric logic in the base Filter class.
"""

from openfilter.filter_runtime.filter import Filter
from openfilter.observability import MetricSpec


class OCRFilter(Filter):
    """Example OCR filter that demonstrates MetricSpec declarations.
    
    This filter declares safe metrics for OCR processing that will be
    aggregated by OpenTelemetry and exported to OpenLineage as heartbeat
    facets without any PII.
    """
    
    metric_specs = [
        # Total frames processed
        MetricSpec(
            name="frames_processed",
            instrument="counter",
            value_fn=lambda d: 1
        ),
        
        # Frames that contain text
        MetricSpec(
            name="frames_with_text",
            instrument="counter",
            value_fn=lambda d: 1 if d.get("text") else 0
        ),
        
        # Distribution of characters per frame
        MetricSpec(
            name="chars_per_frame",
            instrument="histogram",
            value_fn=lambda d: len(d.get("text", "")),
            boundaries=[0, 10, 20, 50, 100, 200]
        ),
        
        # Number of text regions detected
        MetricSpec(
            name="text_regions_per_frame",
            instrument="histogram",
            value_fn=lambda d: len(d.get("text_regions", [])),
            boundaries=[0, 1, 2, 5, 10]
        ),
        
        # Average confidence of OCR results
        MetricSpec(
            name="ocr_confidence",
            instrument="histogram",
            value_fn=lambda d: sum([r.get("confidence", 0) for r in d.get("text_regions", [])]) / max(len(d.get("text_regions", [])), 1),
            boundaries=[0.0, 0.5, 0.7, 0.8, 0.9, 1.0]
        )
    ]
    
    def process(self, frames):
        """Process frames and add OCR results.
        
        This is a simplified example - in a real implementation,
        you would perform actual OCR processing here.
        """
        # Example processing - in reality this would do actual OCR
        for frame in frames.values():
            if hasattr(frame, 'data'):
                # Simulate OCR results
                frame.data["text"] = "ABC123 XYZ789"
                frame.data["text_regions"] = [
                    {"text": "ABC123", "confidence": 0.85, "bbox": [100, 100, 200, 150]},
                    {"text": "XYZ789", "confidence": 0.92, "bbox": [300, 100, 400, 150]}
                ]
        
        return frames 