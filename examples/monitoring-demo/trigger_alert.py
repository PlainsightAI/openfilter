#!/usr/bin/env python3
"""
Trigger real alert rules by running pipelines under conditions that fire them.

Modes:
  gpu     - Run a pipeline normally. On macOS (no nvidia-smi), openfilter_gpu_accessible
            stays 0, firing GPUUnavailable after ~90s.
  camera  - Post a synthetic CameraDisconnected alert to Alertmanager. VideoIn crashes
            on invalid sources (cannot export metrics), so we inject the alert directly
            to verify Alertmanager routes it to Slack correctly.
  disk    - Run a pipeline normally. The test rule DiskCriticalTest (>10% disk usage)
            fires on virtually any machine after ~60s.
  all     - Run all three modes sequentially.

The script polls Alertmanager every 5s and reports when each expected alert appears.

Usage:
    python trigger_alert.py --alert gpu
    python trigger_alert.py --alert camera
    python trigger_alert.py --alert disk
    python trigger_alert.py --alert all
"""
import argparse
import json
import logging
import multiprocessing
import os
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone

# Ensure openfilter is importable when running from the examples directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

ALERTMANAGER_URL = "http://localhost:9093"
POLL_INTERVAL = 5
TIMEOUT = 180  # 3 minutes

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-8s %(message)s")
logger = logging.getLogger(__name__)


def setup_telemetry_env(exporter="otlp", endpoint="http://localhost:4317"):
    """Set telemetry env vars before importing openfilter."""
    os.environ["TELEMETRY_EXPORTER_ENABLED"] = "true"
    os.environ["TELEMETRY_EXPORTER_TYPE"] = exporter
    os.environ["TELEMETRY_EXPORTER_OTLP_ENDPOINT"] = endpoint
    os.environ["EXPORT_INTERVAL"] = "10000"


def get_video_path():
    return os.path.abspath(
        os.path.join(os.path.dirname(__file__), '..', 'hello-world', 'example_video.mp4')
    )


def run_pipeline_normal(duration=120):
    """Run a normal pipeline (fires GPUUnavailable on macOS, DiskCriticalTest everywhere)."""
    setup_telemetry_env()
    from openfilter.filter_runtime.filter import Filter
    from openfilter.filter_runtime.filters.video_in import VideoIn
    from openfilter.filter_runtime.test import FiltersToQueue

    video_path = get_video_path()
    source_uri = f"file://{video_path}!loop!maxfps=5"

    runner = Filter.Runner([
        (VideoIn, dict(
            sources=source_uri,
            outputs="ipc://trigger-alert",
        )),
        (FiltersToQueue, dict(
            sources="ipc://trigger-alert",
            queue=(FiltersToQueue.Queue()).child_queue,
        )),
    ], exit_time=duration)

    return runner


def post_synthetic_alert(am_url, labels, annotations, hours=24):
    """Post a synthetic alert to Alertmanager with endsAt set far in the future."""
    ends_at = (datetime.now(timezone.utc) + timedelta(hours=hours)).strftime(
        "%Y-%m-%dT%H:%M:%S.000Z"
    )
    alert = [{"labels": labels, "annotations": annotations, "endsAt": ends_at}]
    payload = json.dumps(alert).encode("utf-8")
    req = urllib.request.Request(
        f"{am_url}/api/v2/alerts",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return resp.status == 200


def poll_alertmanager(expected_alerts, am_url=ALERTMANAGER_URL, timeout=TIMEOUT):
    """Poll Alertmanager until all expected alerts appear or timeout."""
    logger.info(f"Polling Alertmanager for alerts: {expected_alerts}")
    logger.info(f"  URL: {am_url}/api/v2/alerts")
    logger.info(f"  Timeout: {timeout}s, polling every {POLL_INTERVAL}s")

    found = set()
    start = time.time()

    while time.time() - start < timeout:
        try:
            url = f"{am_url}/api/v2/alerts"
            with urllib.request.urlopen(url, timeout=10) as resp:
                alerts = json.loads(resp.read())
                for alert in alerts:
                    name = alert.get("labels", {}).get("alertname", "")
                    if name in expected_alerts and name not in found:
                        found.add(name)
                        elapsed = int(time.time() - start)
                        logger.info(f"  FOUND: {name} (after {elapsed}s)")
        except Exception as e:
            logger.warning(f"  Poll error: {e}")

        if found == set(expected_alerts):
            logger.info("All expected alerts found!")
            return True

        remaining = set(expected_alerts) - found
        elapsed = int(time.time() - start)
        logger.info(f"  [{elapsed}s] Waiting for: {sorted(remaining)}")
        time.sleep(POLL_INTERVAL)

    missing = set(expected_alerts) - found
    logger.error(f"TIMEOUT: alerts not found after {timeout}s: {sorted(missing)}")
    return False


def trigger_gpu(am_url):
    """Trigger GPUUnavailable alert (fires on macOS where nvidia-smi is absent)."""
    print("\n=== Triggering GPUUnavailable ===")
    print("Running a normal pipeline. On macOS, openfilter_gpu_accessible = 0,")
    print("so GPUUnavailable should fire after ~90s (30s 'for' + metric propagation).")
    print()

    runner = run_pipeline_normal(duration=TIMEOUT)
    try:
        ok = poll_alertmanager(["GPUUnavailable"], am_url=am_url)
    finally:
        runner.stop()
    return ok


def trigger_camera(am_url):
    """Trigger CameraDisconnected by posting a synthetic alert to Alertmanager.

    VideoIn crashes on invalid sources before it can export metrics, so we
    inject the alert directly to verify Alertmanager routes it to Slack.
    """
    print("\n=== Triggering CameraDisconnected ===")
    print("Posting synthetic CameraDisconnected alert to Alertmanager.")
    print("(VideoIn crashes on invalid sources, so we inject the alert directly")
    print("to verify Alertmanager routes it to Slack correctly.)")
    print()

    try:
        ok = post_synthetic_alert(
            am_url,
            labels={
                "alertname": "CameraDisconnected",
                "severity": "critical",
                "pipeline_instance_id": "trigger-alert-camera-test",
            },
            annotations={
                "summary": "Camera disconnected on pipeline trigger-alert-camera-test",
                "description": "Synthetic alert from trigger_alert.py to verify Slack routing. "
                "Run 'make resolve-test-alert' or wait 24h for auto-resolve.",
            },
        )
        if ok:
            logger.info("  FOUND: CameraDisconnected (synthetic, posted directly)")
        return ok
    except Exception as e:
        logger.error(f"  Failed to post synthetic alert: {e}")
        return False


def trigger_disk(am_url):
    """Trigger DiskCriticalTest (>10% threshold, fires on virtually any machine)."""
    print("\n=== Triggering DiskCriticalTest ===")
    print("Running a normal pipeline. The test alert rule DiskCriticalTest fires when")
    print("disk usage > 10%, which is true on virtually any machine.")
    print("Should fire after ~60s (15s 'for' + metric propagation).")
    print()

    runner = run_pipeline_normal(duration=TIMEOUT)
    try:
        ok = poll_alertmanager(["DiskCriticalTest"], am_url=am_url)
    finally:
        runner.stop()
    return ok


def main():
    parser = argparse.ArgumentParser(
        description="Trigger real alert rules by running pipelines"
    )
    parser.add_argument(
        "--alert",
        required=True,
        choices=["gpu", "camera", "disk", "all"],
        help="Which alert to trigger",
    )
    parser.add_argument(
        "--alertmanager-url",
        default=ALERTMANAGER_URL,
        help=f"Alertmanager URL (default: {ALERTMANAGER_URL})",
    )
    args = parser.parse_args()

    # Check Alertmanager is reachable before starting pipelines
    try:
        with urllib.request.urlopen(f"{args.alertmanager_url}/-/healthy", timeout=5):
            pass
    except Exception as e:
        logger.error(f"Alertmanager not reachable at {args.alertmanager_url}: {e}")
        logger.error("Make sure the monitoring stack is running: make stack-up")
        sys.exit(1)

    results = {}

    if args.alert in ("gpu", "all"):
        results["GPUUnavailable"] = trigger_gpu(args.alertmanager_url)

    if args.alert in ("camera", "all"):
        results["CameraDisconnected"] = trigger_camera(args.alertmanager_url)

    if args.alert in ("disk", "all"):
        results["DiskCriticalTest"] = trigger_disk(args.alertmanager_url)

    # Summary
    print("\n" + "=" * 40)
    print("Results:")
    all_ok = True
    for alert_name, ok in results.items():
        status = "PASS" if ok else "FAIL"
        if not ok:
            all_ok = False
        print(f"  {status}: {alert_name}")

    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    multiprocessing.set_start_method("spawn", force=True)
    main()
