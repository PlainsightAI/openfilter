#!/usr/bin/env python3
"""
Run a minimal OpenFilter pipeline that exports health metrics to the monitoring stack.

Pipeline: VideoIn -> FiltersToQueue (sink)

Metrics exported:
  - openfilter_camera_connected   (gauge, 0 or 1)
  - openfilter_disk_usage_percent (gauge, 0-100)
  - openfilter_ram_usage_percent  (gauge, 0-100)
  - openfilter_gpu_accessible     (gauge, 0 or 1)
  - openfilter_gpu_usage_percent  (gauge, 0-100)

Usage:
    # With defaults (OTLP to localhost:4317, 120s runtime)
    python run_pipeline.py

    # Custom video source and runtime
    python run_pipeline.py --source /path/to/video.mp4 --duration 60

    # With console exporter (no monitoring stack needed)
    python run_pipeline.py --exporter console
"""
import argparse
import logging
import multiprocessing
import os
import sys

# Ensure openfilter is importable when running from the examples directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))


def main():
    parser = argparse.ArgumentParser(description="Run a pipeline with health metric export")
    parser.add_argument(
        "--source",
        default=os.path.join(os.path.dirname(__file__), '..', 'hello-world', 'example_video.mp4'),
        help="Path to a video file (default: examples/hello-world/example_video.mp4)",
    )
    parser.add_argument("--duration", type=int, default=120, help="Pipeline runtime in seconds (default: 120)")
    parser.add_argument("--exporter", default="otlp", choices=["otlp", "console", "silent"], help="Telemetry exporter type (default: otlp)")
    parser.add_argument("--endpoint", default="http://localhost:4317", help="OTLP gRPC endpoint (default: http://localhost:4317)")
    parser.add_argument("--export-interval", type=int, default=10000, help="Export interval in ms (default: 10000)")
    parser.add_argument("--maxfps", type=int, default=5, help="Max frames per second (default: 5)")
    args = parser.parse_args()

    # Set telemetry env vars before importing openfilter
    os.environ["TELEMETRY_EXPORTER_ENABLED"] = "true"
    os.environ["TELEMETRY_EXPORTER_TYPE"] = args.exporter
    os.environ["TELEMETRY_EXPORTER_OTLP_ENDPOINT"] = args.endpoint
    os.environ["EXPORT_INTERVAL"] = str(args.export_interval)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-8s %(message)s")
    logger = logging.getLogger(__name__)

    from openfilter.filter_runtime.filter import Filter
    from openfilter.filter_runtime.filters.video_in import VideoIn
    from openfilter.filter_runtime.test import FiltersToQueue

    video_path = os.path.abspath(args.source)
    if not os.path.isfile(video_path):
        logger.error(f"Video file not found: {video_path}")
        sys.exit(1)

    source_uri = f"file://{video_path}!loop!maxfps={args.maxfps}"
    logger.info(f"Source:   {source_uri}")
    logger.info(f"Exporter: {args.exporter} -> {args.endpoint}")
    logger.info(f"Duration: {args.duration}s")

    runner = Filter.Runner([
        (VideoIn, dict(
            sources=source_uri,
            outputs="ipc://monitoring-demo",
        )),
        (FiltersToQueue, dict(
            sources="ipc://monitoring-demo",
            queue=(queue := FiltersToQueue.Queue()).child_queue,
        )),
    ], exit_time=args.duration)

    logger.info("Pipeline running — health metrics are being exported")
    runner.wait()
    logger.info("Pipeline finished")


if __name__ == "__main__":
    multiprocessing.set_start_method("spawn", force=True)
    main()
