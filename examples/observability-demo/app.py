#!/usr/bin/env python3
"""
OpenFilter Observability Demo

This example demonstrates the complete observability system in OpenFilter,
showing how to use both standard filters and custom filters with and without
MetricSpec declarations.

Pipeline: VideoIn → CustomProcessor (with MetricSpecs) → CustomVisualizer (without MetricSpecs) → VideoOut
"""

import os
import logging
import argparse
from pathlib import Path

# Add the project root to Python path for imports
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from openfilter.filter_runtime import Filter
from openfilter.filter_runtime.filters.video_in import VideoIn
from openfilter.filter_runtime.filters.webvis import Webvis

# Import our custom filters
from custom_processor import CustomProcessor, CustomProcessorConfig
from custom_visualizer import CustomVisualizer, CustomVisualizerConfig


def build_pipeline(args):
    """Build the observability demo pipeline."""
    
    # Create output directory
    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)
    
    # Configure output paths
    processed_output = f"file://{output_dir / 'processed_video.mp4'}!fps={args.fps}"
    analytics_output = f"file://{output_dir / 'analytics.json'}"
    
    logging.info(f"Output directory: {output_dir.absolute()}")
    logging.info(f"Processed video: {processed_output}")
    logging.info(f"Analytics data: {analytics_output}")
    
    return [
        # Input video source (standard filter)
        (VideoIn, dict(
            id="video_in",
            sources=f"{args.input}!resize=640x480lin!loop",
            outputs="tcp://*:6000"
        )),
        
        # Custom processor with MetricSpecs (business metrics)
        (CustomProcessor, CustomProcessorConfig(
            id="custom_processor",
            sources="tcp://127.0.0.1:6000",
            outputs="tcp://*:6002",
            detection_threshold=args.detection_threshold,
            max_detections=args.max_detections,
            add_confidence_scores=True,
            add_bounding_boxes=True,
            # mq_log="pretty"
        )),
        
        # Custom visualizer without MetricSpecs (system metrics only)
        (CustomVisualizer, CustomVisualizerConfig(
            id="custom_visualizer",
            sources="tcp://127.0.0.1:6002",
            outputs="tcp://*:6004",
            draw_detections=True,
            draw_confidence=True,
            draw_bounding_boxes=True,
            overlay_text=True,
            # mq_log="pretty"
        )),
        
        (Webvis, dict(
            id="webvis",
            sources="tcp://127.0.0.1:6004",
            host="0.0.0.0",
            port=8000,
        ))
    ]


def main():
    """Main application entry point."""
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )
    logger = logging.getLogger(__name__)
    
    try:
        # Parse command line arguments
        parser = argparse.ArgumentParser(
            description="OpenFilter Observability Demo",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
Examples:
  # Basic run with console output
  python app.py
  
  # With OpenTelemetry enabled
  export TELEMETRY_EXPORTER_ENABLED=true
  python app.py
  
  # With OpenLineage enabled
  export TELEMETRY_EXPORTER_ENABLED=true
  export OPENLINEAGE_URL=https://oleander.dev
  export OPENLINEAGE_API_KEY=your_api_key
  python app.py
            """
        )
        
        parser.add_argument(
            "--input",
            default="file://examples/observability-demo/sample_video.mp4!loop",
            help="Input video URI (default: sample_video.mp4)"
        )
        parser.add_argument(
            "--fps", 
            type=int,
            default=30,
            help="Output FPS (default: 30)"
        )
        parser.add_argument(
            "--detection-threshold",
            type=float,
            default=0.5,
            help="Detection confidence threshold (default: 0.5)"
        )
        parser.add_argument(
            "--max-detections",
            type=int,
            default=10,
            help="Maximum detections per frame (default: 10)"
        )
        
        args = parser.parse_args()
        
        # Log startup information
        logger.info("🚀 Starting OpenFilter Observability Demo")
        logger.info(f"📹 Video source: {args.input}")
        logger.info(f"🎬 Output FPS: {args.fps}")
        logger.info(f"🎯 Detection threshold: {args.detection_threshold}")
        logger.info(f"🔢 Max detections: {args.max_detections}")
        
        # Check observability configuration
        telemetry_enabled = os.getenv("TELEMETRY_EXPORTER_ENABLED", "false").lower() in ("true", "1")
        openlineage_url = os.getenv("OPENLINEAGE_URL")
        
        if telemetry_enabled:
            logger.info("✅ OpenTelemetry enabled - system metrics will be exported")
            if openlineage_url:
                logger.info(f"✅ OpenLineage enabled - business metrics will be exported to {openlineage_url}")
            else:
                logger.info("ℹ️  OpenLineage not configured - business metrics will not be exported")
        else:
            logger.info("ℹ️  OpenTelemetry disabled - no metrics will be exported")
        
        # Build and run the pipeline
        pipeline = build_pipeline(args)
        logger.info(f"🔗 Pipeline: {' → '.join([f[0].__name__ for f in pipeline])}")
        
        Filter.run_multi(pipeline)
        
    except KeyboardInterrupt:
        logger.info("⏹️  Pipeline stopped by user")
    except Exception as e:
        logger.error(f"❌ Pipeline failed: {str(e)}", exc_info=True)
        raise


if __name__ == "__main__":
    main() 