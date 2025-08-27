#!/usr/bin/env python3
"""
Custom processor filter with MetricSpec declarations.

This filter demonstrates how to declare metrics using MetricSpec
and shows automatic histogram bucket generation.
"""

import random
import time
from typing import Dict, Any
from openfilter.filter_runtime import Filter, Frame, FilterConfig
from openfilter.observability import MetricSpec


class CustomProcessorConfig(FilterConfig):
    """Configuration for the custom processor filter."""
    mq_log: str | bool | None = None


class CustomProcessor(Filter):
    """Custom processor that simulates object detection and adds metrics."""
    
    # Declare metrics using MetricSpec
    metric_specs = [
        # Counters
        MetricSpec(
            name="frames_processed",
            instrument="counter",
            value_fn=lambda d: 1
        ),
        MetricSpec(
            name="frames_with_detections", 
            instrument="counter",
            value_fn=lambda d: 1 if d.get("detections") else 0
        ),
        
        # Histograms with auto-generated buckets
        MetricSpec(
            name="detections_per_frame",
            instrument="histogram",
            value_fn=lambda d: len(d.get("detections", [])),
            num_buckets=8  # Auto-generate 8 buckets for 0-50 detections
        ),
        MetricSpec(
            name="detection_confidence",
            instrument="histogram", 
            value_fn=lambda d: d.get("avg_confidence", 0.0),
            num_buckets=8  # Auto-generate 8 buckets for 0.0-1.0 confidence
        ),
        MetricSpec(
            name="processing_time_ms",
            instrument="histogram",
            value_fn=lambda d: d.get("processing_time", 0.0),
            num_buckets=12  # Auto-generate 12 buckets for 0-100ms
        ),
        
        # Custom boundaries for specific metrics
        MetricSpec(
            name="object_size_ratio",
            instrument="histogram",
            value_fn=lambda d: d.get("size_ratio", 0.0),
            boundaries=[0.0, 0.1, 0.2, 0.3, 0.5, 0.7, 1.0]  # Custom boundaries
        )
    ]
    
    def setup(self, config):
        """Setup the filter."""
        self.config = config
        print(f"[CustomProcessor] Setup complete with config: {config}")
    
    def process(self, frames: Dict[str, Frame]) -> Dict[str, Frame]:
        """Process frames and add detection data."""
        processed_frames = {}
        
        for frame_id, frame in frames.items():
            # Simulate object detection
            num_detections = random.randint(0, 8)
            detections = []
            
            if num_detections > 0:
                # Generate fake detections
                for i in range(num_detections):
                    confidence = random.uniform(0.3, 0.95)
                    detections.append({
                        "id": i,
                        "class": random.choice(["person", "car", "bicycle", "dog"]),
                        "confidence": confidence,
                        "bbox": [random.uniform(0, 1) for _ in range(4)]
                    })
            
            # Calculate average confidence
            avg_confidence = sum(d["confidence"] for d in detections) / len(detections) if detections else 0.0
            
            # Simulate processing time
            processing_time = random.uniform(5.0, 45.0)
            
            # Calculate size ratio (simulated)
            size_ratio = random.uniform(0.05, 0.8)
            
            # Update frame data with detection results
            frame.data.update({
                "detections": detections,
                "num_detections": num_detections,
                "avg_confidence": avg_confidence,
                "processing_time": processing_time,
                "size_ratio": size_ratio,
                "timestamp": time.time()  # Use current time instead of frame.timestamp
            })
            
            processed_frames[frame_id] = frame
        
        return processed_frames 