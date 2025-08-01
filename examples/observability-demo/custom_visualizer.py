#!/usr/bin/env python3
"""
Custom Visualizer Filter without MetricSpec Declarations

This filter demonstrates backward compatibility - it works without MetricSpec
declarations and only emits system metrics to OpenTelemetry.
"""

import logging
from typing import Dict, Any, List
from openfilter.filter_runtime import Filter, FilterConfig

logger = logging.getLogger(__name__)


class CustomVisualizerConfig(FilterConfig):
    """Configuration for the CustomVisualizer filter."""
    id: str
    sources: str
    outputs: str
    draw_detections: bool = True
    draw_confidence: bool = True
    draw_bounding_boxes: bool = True
    overlay_text: bool = True
    mq_log: str | bool | None = None


class CustomVisualizer(Filter):
    """
    Custom visualizer that creates overlays on processed frames.
    
    This filter demonstrates:
    1. Backward compatibility without MetricSpec declarations
    2. System metrics only (CPU, memory, FPS)
    3. No business metrics (no MetricSpecs declared)
    """
    
    # No MetricSpec declarations - this filter only emits system metrics
    # metric_specs = []  # Default empty list
    
    def setup(self, config: CustomVisualizerConfig):
        """Setup the visualizer."""
        
        # Initialize configuration from config
        self.draw_detections = config.draw_detections
        self.draw_confidence = config.draw_confidence
        self.draw_bounding_boxes = config.draw_bounding_boxes
        self.overlay_text = config.overlay_text
        
        logger.info(f"CustomVisualizer setup complete with draw_detections={self.draw_detections}")
    
    def process(self, frames: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process frames and add visual overlays.
        
        This method creates visual overlays on frames based on detection data.
        Since this filter has no MetricSpec declarations, it only emits
        system metrics (CPU, memory, FPS) to OpenTelemetry.
        """
        processed_frames = {}
        
        for topic, frame in frames.items():
            if frame is None:
                continue
            
            # Get detection data from frame
            detections = []
            if hasattr(frame, 'data') and frame.data:
                detections = frame.data.get("detections", [])
            
            # Create visual overlay information
            overlay_data = self._create_overlay_data(frame, detections)
            
            frame.data.update({
                "overlay_data": overlay_data,
                "visualization_applied": True
            })
            
            processed_frames[topic] = frame
            
            # Log visualization info
            if detections:
                logger.debug(f"Frame visualized: {len(detections)} detections, overlay applied")
        
        return processed_frames
    
    def _create_overlay_data(self, frame, detections: List) -> Dict[str, Any]:
        """
        Create overlay data for visualization.
        
        This method generates overlay information that would be used
        to draw visual elements on the frame (bounding boxes, labels, etc.).
        """
        overlay_data = {
            "elements": [],
            "text_overlays": [],
            "statistics": {}
        }
        
        if not detections:
            return overlay_data
        
        # Create bounding box overlays
        if self.draw_bounding_boxes:
            for i, detection in enumerate(detections):
                bbox_element = {
                    "type": "bounding_box",
                    "x": detection["x"],
                    "y": detection["y"],
                    "width": detection["width"],
                    "height": detection["height"],
                    "confidence": detection["confidence"],
                    "class": detection["class_name"],
                    "color": self._get_color_for_confidence(detection["confidence"])
                }
                overlay_data["elements"].append(bbox_element)
        
        # Create confidence score overlays
        if self.draw_confidence:
            for i, detection in enumerate(detections):
                confidence_text = {
                    "type": "text",
                    "x": detection["x"],
                    "y": detection["y"] - 10,
                    "text": f"{detection['confidence']:.2f}",
                    "color": self._get_color_for_confidence(detection["confidence"]),
                    "font_size": 12
                }
                overlay_data["text_overlays"].append(confidence_text)
        
        # Create statistics overlay
        if self.overlay_text:
            stats_text = {
                "type": "text",
                "x": 10,
                "y": 30,
                "text": f"Detections: {len(detections)}",
                "color": "white",
                "font_size": 16
            }
            overlay_data["text_overlays"].append(stats_text)
            
            if detections:
                max_confidence = max([d["confidence"] for d in detections])
                confidence_text = {
                    "type": "text",
                    "x": 10,
                    "y": 50,
                    "text": f"Max Confidence: {max_confidence:.2f}",
                    "color": "white",
                    "font_size": 16
                }
                overlay_data["text_overlays"].append(confidence_text)
        
        # Add statistics
        overlay_data["statistics"] = {
            "total_detections": len(detections),
            "max_confidence": max([d["confidence"] for d in detections], default=0.0),
            "classes_detected": list(set([d["class_name"] for d in detections])),
            "average_confidence": sum([d["confidence"] for d in detections]) / len(detections) if detections else 0.0
        }
        
        return overlay_data
    
    def _get_color_for_confidence(self, confidence: float) -> str:
        """Get color based on confidence score."""
        if confidence >= 0.8:
            return "green"
        elif confidence >= 0.6:
            return "yellow"
        elif confidence >= 0.4:
            return "orange"
        else:
            return "red"
    
    def shutdown(self):
        """Cleanup resources."""
        logger.info("CustomVisualizer shutdown complete")
        super().shutdown() 