#!/usr/bin/env python3
"""
Custom Processor Filter with MetricSpec Declarations

This filter demonstrates how to declare business metrics using MetricSpec
and safely extract metrics from frame.data without exposing PII.
"""

import random
import logging
from typing import Dict, Any, List
from dataclasses import dataclass

from openfilter.filter_runtime import Filter, FilterConfig
from openfilter.observability import MetricSpec

logger = logging.getLogger(__name__)


@dataclass
class Detection:
    """Represents a detection with bounding box and confidence."""
    x: int
    y: int
    width: int
    height: int
    confidence: float
    class_name: str


class CustomProcessorConfig(FilterConfig):
    """Configuration for the CustomProcessor filter."""
    id: str
    sources: str
    outputs: str
    detection_threshold: float = 0.5
    max_detections: int = 10
    add_confidence_scores: bool = True
    add_bounding_boxes: bool = True


class CustomProcessor(Filter):
    """
    Custom processor that simulates object detection and declares business metrics.
    
    This filter demonstrates:
    1. MetricSpec declarations for business metrics
    2. Safe metric extraction from frame.data
    3. No PII exposure in metrics
    """
    
    # Declare business metrics using MetricSpec
    metric_specs = [
        # Total frames processed
        MetricSpec(
            name="frames_processed",
            instrument="counter",
            value_fn=lambda d: 1  # Count every frame
        ),
        
        # Frames with detections
        MetricSpec(
            name="frames_with_detections", 
            instrument="counter",
            value_fn=lambda d: 1 if d.get("detections") else 0
        ),
        
        # Number of detections per frame (histogram)
        MetricSpec(
            name="detections_per_frame",
            instrument="histogram", 
            value_fn=lambda d: len(d.get("detections", [])),
            boundaries=[0, 1, 2, 3, 5, 10]  # Buckets for detection counts
        ),
        
        # Detection confidence scores (histogram)
        MetricSpec(
            name="detection_confidence",
            instrument="histogram",
            value_fn=lambda d: max([d.get("max_confidence", 0.0)], default=0.0),
            boundaries=[0.0, 0.3, 0.5, 0.7, 0.9, 1.0]  # Confidence buckets
        )
    ]
    
    def setup(self, config: CustomProcessorConfig):
        """Setup the processor."""
        
        # Initialize configuration from config
        self.detection_threshold = config.detection_threshold
        self.max_detections = config.max_detections
        self.add_confidence_scores = config.add_confidence_scores
        self.add_bounding_boxes = config.add_bounding_boxes
        
        logger.info(f"CustomProcessor setup complete with threshold={self.detection_threshold}, max_detections={self.max_detections}")
    
    def process(self, frames: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process frames and add detection data.
        
        This method simulates object detection and adds safe metrics to frame.data.
        The metrics are declared via MetricSpec and will be automatically recorded
        by the TelemetryRegistry.
        """
        processed_frames = {}
        
        for topic, frame in frames.items():
            if frame is None:
                continue
                
            # Simulate object detection
            detections = self._simulate_detections(frame)
            
            # Add detection information (safe for metrics)
            # Convert Detection objects to dictionaries for JSON serialization
            detection_dicts = [
                {
                    "x": d.x, "y": d.y, "width": d.width, "height": d.height,
                    "confidence": d.confidence, "class_name": d.class_name
                }
                for d in detections
            ]
            
            frame.data.update({
                "detections": detection_dicts,
                "detection_count": len(detections),
                "max_confidence": max([d.confidence for d in detections], default=0.0) if detections else 0.0,
                "has_detections": len(detections) > 0
            })
            
            # Add bounding box information if requested
            if self.add_bounding_boxes and detections:
                frame.data["bounding_boxes"] = [
                    {
                        "x": d.x, "y": d.y, 
                        "width": d.width, "height": d.height,
                        "confidence": d.confidence,
                        "class": d.class_name
                    }
                    for d in detections
                ]
            
            # Add confidence scores if requested
            if self.add_confidence_scores and detections:
                frame.data["confidence_scores"] = [d.confidence for d in detections]
            
            processed_frames[topic] = frame
            
            # Log processing info
            if len(detections) > 0:
                logger.debug(f"Frame processed: {len(detections)} detections, max confidence: {max([d.confidence for d in detections]):.2f}")
        
        return processed_frames
    
    def _simulate_detections(self, frame) -> List[Detection]:
        """
        Simulate object detection on a frame.
        
        This is a mock implementation that generates random detections
        for demonstration purposes. In a real implementation, this would
        call an actual object detection model.
        """
        detections = []
        
        # Simulate random number of detections (0-5)
        num_detections = random.randint(0, min(5, self.max_detections))
        
        # Available object classes for simulation
        classes = ["person", "car", "dog", "cat", "bicycle"]
        
        for _ in range(num_detections):
            # Generate random confidence score
            confidence = random.uniform(0.1, 1.0)
            
            # Only include detections above threshold
            if confidence >= self.detection_threshold:
                # Generate random bounding box
                x = random.randint(0, 600)
                y = random.randint(0, 400)
                width = random.randint(50, 200)
                height = random.randint(50, 200)
                
                # Ensure bounding box fits in frame
                if x + width > 640:
                    width = 640 - x
                if y + height > 480:
                    height = 480 - y
                
                detection = Detection(
                    x=x, y=y, width=width, height=height,
                    confidence=confidence,
                    class_name=random.choice(classes)
                )
                
                detections.append(detection)
        
        return detections
    
    def shutdown(self):
        """Cleanup resources."""
        logger.info("CustomProcessor shutdown complete")
        super().shutdown() 