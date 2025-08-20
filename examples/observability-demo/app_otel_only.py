#!/usr/bin/env python3
"""
OTEL-Only Observability Demo

This demo shows how to use OpenFilter with OTEL collectors only,
without OpenLineage. It demonstrates:
1. Raw metrics sent directly to OTEL collectors
2. Aggregated metrics processed by OTel SDK
3. Custom MetricSpec definitions with target="otel"
4. Connection to cloud OTEL endpoints

Usage:
    python app_otel_only.py
"""

import os
import sys
import signal
import time
import logging
import argparse
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from openfilter.filter_runtime.filter import Filter
from openfilter.filter_runtime.filters.video_in import VideoIn
from openfilter.filter_runtime.filters.video_out import VideoOut
from openfilter.filter_runtime.filters.webvis import Webvis

from custom_processor import CustomProcessorConfig, CustomProcessor
from custom_visualizer import CustomVisualizerConfig, CustomVisualizer
from create_sample_video import create_sample_video


def build_otel_pipeline(args):
    """Build the OTEL-only observability pipeline."""
    
    # Create output directory
    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)
    
    # Create sample video if it doesn't exist and no input specified
    sample_video = Path(__file__).parent / "sample_video.mp4"
    if args.input == "sample_video.mp4" and not sample_video.exists():
        print("📹 Creating sample video...")
        create_sample_video(str(sample_video))
    
    # Configure output paths
    video_output = f"file://{output_dir / 'otel_demo_output.mp4'}!fps={args.fps}"
    analytics_output = f"file://{output_dir / 'otel_analytics.json'}"
    
    logging.info(f"📹 Input video: {args.input}")
    logging.info(f"📤 Output video: {video_output}")
    logging.info(f"📊 Analytics data: {analytics_output}")
    
    return [
        # Input video source (standard filter)
        (VideoIn, dict(
            id="video_in",
            sources=f"{args.input}!resize=640x480lin",
            outputs="tcp://*:6000"
        )),
        
        # Custom processor with MetricSpecs (business metrics)
        (CustomProcessor, CustomProcessorConfig(
            id="custom_processor",
            sources="tcp://127.0.0.1:6000",
            outputs="tcp://*:6002",
            detection_threshold=args.detection_threshold,
            export_mode="both",  # Send both raw and aggregated
            target="otel",       # Only to OTEL, not OpenLineage
            # mq_log="pretty"
        )),
        
        # Custom visualizer without MetricSpecs (system metrics only)
        (CustomVisualizer, CustomVisualizerConfig(
            id="custom_visualizer", 
            sources="tcp://127.0.0.1:6002",
            outputs="tcp://*:6004",
            # mq_log="pretty"
        )),
        
        (Webvis, dict(
            id="webvis",
            sources="tcp://127.0.0.1:6004",
            host="0.0.0.0",
            port=8000,
        ))
    ]



def signal_handler(signum, frame):
    """Handle shutdown signals gracefully."""
    print(f"\n🛑 Received signal {signum}, shutting down...")
    sys.exit(0)


def main():
    """Main entry point for OTEL-only demo."""
    
    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger(__name__)
    
    # Set up signal handling
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # Parse command line arguments
        parser = argparse.ArgumentParser(
            description="OpenFilter OTEL-Only Observability Demo",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
Examples:
  # Basic demo with sample video
  python app_otel_only.py
  
  # Custom video input
  python app_otel_only.py --input file://your_video.mp4
  
  # With webcam input
  python app_otel_only.py --input webcam://0
  
  # Custom settings
  python app_otel_only.py --input file://video.mp4 --fps 30 --detection-threshold 0.7
            """
        )
        parser.add_argument(
            "--input",
            default="sample_video.mp4",
            help="Video input source (default: sample_video.mp4)"
        )
        parser.add_argument(
            "--fps",
            type=int,
            default=10,
            help="Output video FPS (default: 10)"
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
        logger.info("🚀 Starting OTEL-Only Observability Demo")
        logger.info(f"📹 Video source: {args.input}")
        logger.info(f"🎬 Output FPS: {args.fps}")
        logger.info(f"🎯 Detection threshold: {args.detection_threshold}")
        logger.info(f"🔢 Max detections: {args.max_detections}")
        
        # Check observability configuration
        otel_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
        telemetry_enabled = os.getenv("TELEMETRY_EXPORTER_ENABLED", "false").lower() in ("true", "1")
        
        if telemetry_enabled:
            logger.info("✅ OpenTelemetry enabled - metrics will be exported to OTEL collectors")
            if otel_endpoint:
                logger.info(f"✅ OTEL endpoint configured: {otel_endpoint}")
            else:
                logger.warning("⚠️  OTEL endpoint not configured - metrics will use console/silent export")
        else:
            logger.info("ℹ️  OpenTelemetry disabled - no metrics will be exported")
        
        logger.info("🎯 Target: OTEL Collectors Only (OpenLineage disabled)")
        logger.info("📈 Export Mode: Raw + Aggregated")
        
        # Load environment configuration from file if exists
        config_file = Path(__file__).parent / "config_otel_only.env"
        if config_file.exists():
            logger.info(f"📄 Loading configuration from {config_file}")
            # Note: In production, use python-dotenv or similar
            with open(config_file) as f:
                for line in f:
                    if line.strip() and not line.startswith('#'):
                        if '=' in line:
                            key, value = line.strip().split('=', 1)
                            os.environ[key] = value
        
        # Build and run the OTEL-only pipeline
        pipeline = build_otel_pipeline(args)
        
        logger.info(f"🔗 Pipeline: {' → '.join([f[0].__name__ for f in pipeline])}")
        logger.info("🎬 Starting video processing...")
        logger.info("Press Ctrl+C to stop")
        
        # Run the pipeline using the correct OpenFilter pattern
        Filter.run_multi(pipeline)
        
    except KeyboardInterrupt:
        logger.info("👋 Demo stopped by user")
    except Exception as e:
        logger.error(f"❌ Error running demo: {str(e)}", exc_info=True)
        return 1
    
    logger.info("✅ OTEL-Only Demo completed successfully!")
    return 0


if __name__ == "__main__":
    main()
