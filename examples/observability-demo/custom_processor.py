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
    detection_threshold: float = 0.5
    export_mode: str = "aggregated"  # 'raw', 'aggregated', 'both'
    target: str = "both"  # 'otel', 'openlineage', 'both'


class CustomProcessor(Filter):
    """Custom processor that simulates object detection and adds metrics."""
    
    def __init__(self, config: CustomProcessorConfig):
        """Initialize the processor with configuration."""
        super().__init__(config)
        # Initialize metric_specs with default values
        self.metric_specs = []
        self.config = config
    
    def setup(self, config: CustomProcessorConfig):
        """Setup the filter with dynamic MetricSpec based on configuration."""
        self.config = config
        
        # Create dynamic metric specs based on config
        self.metric_specs = [
            # Simple test counter - should always show up
            MetricSpec(
                name="test_counter",
                instrument="counter", 
                value_fn=lambda d: 1,  # Always increment by 1
                export_mode=config.export_mode,
                target=config.target
            ),
            # Counters
            MetricSpec(
                name="frames_processed",
                instrument="counter",
                value_fn=lambda d: 1,
                export_mode=config.export_mode,
                target=config.target
            ),
            MetricSpec(
                name="frames_with_detections", 
                instrument="counter",
                value_fn=lambda d: 1 if d.get("detections") else 0,
                export_mode=config.export_mode,
                target=config.target
            ),
            
            # Histograms with auto-generated buckets
            MetricSpec(
                name="detections_per_frame",
                instrument="histogram",
                value_fn=lambda d: len(d.get("detections", [])),
                num_buckets=8,  # Auto-generate 8 buckets for 0-50 detections
                export_mode=config.export_mode,
                target=config.target
            ),
            MetricSpec(
                name="detection_confidence",
                instrument="histogram", 
                value_fn=lambda d: d.get("avg_confidence", 0.0),
                num_buckets=8,  # Auto-generate 8 buckets for 0.0-1.0 confidence
                export_mode=config.export_mode,
                target=config.target
            ),
            MetricSpec(
                name="processing_time_ms",
                instrument="histogram",
                value_fn=lambda d: d.get("processing_time", 0.0),
                num_buckets=12,  # Auto-generate 12 buckets for 0-100ms
                export_mode=config.export_mode,
                target=config.target
            ),
            
            # Custom boundaries for specific metrics
            MetricSpec(
                name="object_size_ratio",
                instrument="histogram",
                value_fn=lambda d: d.get("size_ratio", 0.0),
                boundaries=[0.0, 0.1, 0.2, 0.3, 0.5, 0.7, 1.0],  # Custom boundaries
                export_mode=config.export_mode,
                target=config.target
            )
        ]
        
        print(f"[CustomProcessor] Setup complete with config: {config}")
        print(f"[CustomProcessor] Created {len(self.metric_specs)} MetricSpecs with target='{config.target}', export_mode='{config.export_mode}'")
    
    def process(self, frames: Dict[str, Frame]) -> Dict[str, Frame]:
        """Process frames and add detection data."""
        # print(f"[CustomProcessor] Processing {len(frames)} frames")
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
            
            # Record business metrics for this frame
            if hasattr(self, '_telemetry') and self._telemetry:
                self._telemetry.record(frame.data)
            # else:
            #     print(f"[CustomProcessor] No telemetry registry available!")
            
            processed_frames[frame_id] = frame
        
        return processed_frames 