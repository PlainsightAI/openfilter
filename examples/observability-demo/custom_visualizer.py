#!/usr/bin/env python3
"""
Custom visualizer filter without MetricSpec declarations.

This filter demonstrates backward compatibility - filters without
MetricSpec declarations still work and emit system metrics.
"""

import cv2
import numpy as np
from typing import Dict, Any
from openfilter.filter_runtime import Filter, Frame, FilterConfig


class CustomVisualizerConfig(FilterConfig):
    """Configuration for the custom visualizer filter."""
    mq_log: str | bool | None = None


class CustomVisualizer(Filter):
    """Custom visualizer that adds overlays to processed frames."""
    
    def setup(self, config):
        """Setup the filter."""
        self.config = config
        print(f"[CustomVisualizer] Setup complete with config: {config}")
    
    def process(self, frames: Dict[str, Frame]) -> Dict[str, Frame]:
        """Add visual overlays to frames."""
        processed_frames = {}
        
        for frame_id, frame in frames.items():
            if frame.image is not None:
                # Get detection data from frame
                detections = frame.data.get("detections", [])
                
                # Create a copy of the image for drawing
                overlay_image = frame.image.copy()
                
                # Draw detection boxes
                for detection in detections:
                    if isinstance(detection, dict):
                        # Extract bounding box coordinates
                        bbox = detection.get("bbox", [0, 0, 0.1, 0.1])
                        confidence = detection.get("confidence", 0.0)
                        class_name = detection.get("class", "unknown")
                        
                        # Convert normalized coordinates to pixel coordinates
                        h, w = overlay_image.shape[:2]
                        x1 = int(bbox[0] * w)
                        y1 = int(bbox[1] * h)
                        x2 = int(bbox[2] * w)
                        y2 = int(bbox[3] * h)
                        
                        # Draw bounding box
                        color = (0, 255, 0)  # Green
                        cv2.rectangle(overlay_image, (x1, y1), (x2, y2), color, 2)
                        
                        # Draw label
                        label = f"{class_name}: {confidence:.2f}"
                        cv2.putText(overlay_image, label, (x1, y1-10), 
                                  cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
                
                # Add frame info overlay
                info_text = f"Detections: {len(detections)}"
                cv2.putText(overlay_image, info_text, (10, 30), 
                           cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)

            
            processed_frames[frame_id] = frame
        
        return processed_frames 