#!/usr/bin/env python3
"""
P4 reproducer: diamond pipeline with same-class parallel filters.

Topology:
    VideoIn -> SlowPassthrough(B1, 50ms) --+
                                            +--> TimingFilter(fan-in) -> sink
    VideoIn -> SlowPassthrough(B2, 80ms) --+

Both B1 and B2 are SlowPassthrough instances with different FILTER_IDs and
sleep durations.  This triggers two bugs:

  Bug 1 (metric label collision): B1 and B2 share filter_name=SlowPassthrough
        and pipeline_instance_id, so Prometheus sees only one series.

  Bug 2 (wrong aggregate timing): _inject_timings picks the first topic's
        timing chain for aggregates.  In fan-in, that may be the short branch
        instead of the critical path (slowest branch).

Usage:
    python run_pipeline_p4.py --exporter console --duration 30
"""
import argparse
import logging
import multiprocessing
import os
import sys

# Ensure openfilter is importable when running from the examples directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, os.path.dirname(__file__))


def main():
    parser = argparse.ArgumentParser(description="P4 diamond-same-class reproducer")
    parser.add_argument(
        "--source",
        default=os.path.join(os.path.dirname(__file__), '..', 'hello-world', 'example_video.mp4'),
        help="Path to a video file",
    )
    parser.add_argument("--duration", type=int, default=30, help="Pipeline runtime in seconds")
    parser.add_argument("--exporter", default="otlp", choices=["otlp", "console", "silent"])
    parser.add_argument("--endpoint", default="http://localhost:4317")
    parser.add_argument("--export-interval", type=int, default=10000)
    parser.add_argument("--maxfps", type=int, default=5)
    args = parser.parse_args()

    os.environ["TELEMETRY_EXPORTER_ENABLED"] = "true"
    os.environ["TELEMETRY_EXPORTER_TYPE"] = args.exporter
    os.environ["TELEMETRY_EXPORTER_OTLP_ENDPOINT"] = args.endpoint
    os.environ["EXPORT_INTERVAL"] = str(args.export_interval)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-8s %(message)s")
    logger = logging.getLogger(__name__)

    from openfilter.filter_runtime.filter import Filter
    from openfilter.filter_runtime.filters.video_in import VideoIn
    from openfilter.filter_runtime.test import FiltersToQueue
    from filters.slow_passthrough import SlowPassthrough
    from timing_filter.filter import TimingFilter

    video_path = os.path.abspath(args.source)
    if not os.path.isfile(video_path):
        logger.error(f"Video file not found: {video_path}")
        sys.exit(1)

    source_uri = f"file://{video_path}!loop!maxfps={args.maxfps}"
    logger.info(f"Source:   {source_uri}")
    logger.info(f"Exporter: {args.exporter}")
    logger.info(f"Duration: {args.duration}s")
    logger.info("Topology: VideoIn -> SlowB1(50ms) + SlowB2(80ms) -> TimingFilter -> sink")

    q = FiltersToQueue.Queue()

    runner = Filter.Runner([
        # Source
        (VideoIn, dict(
            id="p4_video_in",
            sources=source_uri,
            outputs="ipc://p4-source",
            pipeline_id="diamond-same-class",
        )),
        # Branch B1 (fast)
        (SlowPassthrough, dict(
            id="p4_slow_b1",
            sources="ipc://p4-source",
            outputs="ipc://p4-b1",
            pipeline_id="diamond-same-class",
            _env={"SLEEP_MS": "50"},
        )),
        # Branch B2 (slow, critical path)
        (SlowPassthrough, dict(
            id="p4_slow_b2",
            sources="ipc://p4-source",
            outputs="ipc://p4-b2",
            pipeline_id="diamond-same-class",
            _env={"SLEEP_MS": "80"},
        )),
        # Fan-in: merge both branches
        (TimingFilter, dict(
            id="p4_timing",
            sources="ipc://p4-b1;>branch_b1, ipc://p4-b2;>branch_b2",
            outputs="ipc://p4-out",
            pipeline_id="diamond-same-class",
        )),
        # Sink
        (FiltersToQueue, dict(
            id="p4_sink",
            sources="ipc://p4-out",
            queue=q.child_queue,
            pipeline_id="diamond-same-class",
        )),
    ], exit_time=args.duration)

    # Capture a few frames and display timing data
    logger.info("Waiting for frames...")
    frames_captured = 0
    try:
        while frames_captured < 5:
            frame = q.get(timeout=30)
            frames_captured += 1
            timings = frame.data.get('meta', {}).get('filter_timings', [])
            if timings:
                print(f"\n=== Frame {frames_captured}: Timing Chain ===")
                for t in timings:
                    fid = t.get('filter_id', '?')
                    print(f"  {t['filter_name']} (id={fid}): {t['duration_ms']:.1f}ms")
                total = sum(t['duration_ms'] for t in timings)
                print(f"  TOTAL: {total:.1f}ms")
                print(f"  Expected: >= 80ms (critical path: SlowB2=80ms + overhead)")
    except Exception as e:
        logger.warning(f"Frame capture stopped: {e}")

    logger.info(f"Captured {frames_captured} frames, waiting for pipeline to finish...")
    runner.wait()
    logger.info("Pipeline finished")


if __name__ == "__main__":
    multiprocessing.set_start_method("spawn", force=True)
    main()
