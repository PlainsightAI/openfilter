#!/usr/bin/env python3
"""
Verify that all 3 multi-pipeline topologies (transform-chain, fan-out, diamond)
are running correctly: infrastructure health, webvis liveness, metric
correctness, and end-to-end frame flow.

Usage:
    python verify_pipelines.py
    python verify_pipelines.py --prometheus-url http://localhost:9090
"""
import argparse
import json
import socket
import sys
import urllib.parse
import urllib.request

# Expected filter class names per pipeline_id.
EXPECTED_FILTERS = {
    "transform-chain": {"VideoIn", "GrayscaleFilter", "ResizeFilter", "TimingFilter", "Webvis"},
    "fan-out": {"VideoIn", "GrayscaleFilter", "ResizeFilter", "TimingFilter", "Webvis"},
    "diamond": {"VideoIn", "GrayscaleFilter", "StatsFilter", "TimingFilter", "Webvis"},
}

PIPELINE_IDS = list(EXPECTED_FILTERS.keys())

WEBVIS_PORTS = {
    "transform-chain": 8001,
    "fan-out": 8002,
    "diamond": 8003,
}


def query_prometheus(base_url, promql):
    url = f"{base_url}/api/v1/query?query={urllib.parse.quote(promql)}"
    with urllib.request.urlopen(url, timeout=5) as resp:
        return json.loads(resp.read())


def http_reachable(url, timeout=3):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


def read_mjpeg_bytes(host, port, max_bytes=65536, timeout=5):
    """Read raw bytes from an MJPEG stream, return them or None on failure."""
    try:
        req = urllib.request.Request(f"http://{host}:{port}/")
        resp = urllib.request.urlopen(req, timeout=timeout)
        data = resp.read(max_bytes)
        resp.close()
        return data
    except Exception:
        return None


class Checker:
    def __init__(self):
        self.passed = 0
        self.failed = 0

    def ok(self, msg):
        print(f"  PASS: {msg}")
        self.passed += 1

    def fail(self, msg):
        print(f"  FAIL: {msg}")
        self.failed += 1

    def check(self, condition, pass_msg, fail_msg):
        if condition:
            self.ok(pass_msg)
        else:
            self.fail(fail_msg)


def main():
    parser = argparse.ArgumentParser(description="Verify multi-pipeline deployment")
    parser.add_argument("--prometheus-url", default="http://localhost:9090")
    parser.add_argument("--otel-url", default="http://localhost:8889")
    args = parser.parse_args()

    c = Checker()

    # ── Phase 1: Infrastructure Health ──────────────────────────────────
    print("== Phase 1: Infrastructure Health ==")

    c.check(
        http_reachable(f"{args.prometheus_url}/-/healthy"),
        "Prometheus is healthy",
        "Prometheus is not reachable",
    )

    c.check(
        http_reachable(f"{args.otel_url}/metrics"),
        "OTEL Collector metrics endpoint is reachable",
        "OTEL Collector metrics endpoint is not reachable",
    )

    # ── Phase 2: Webvis Liveness ────────────────────────────────────────
    print("\n== Phase 2: Webvis Liveness ==")

    for name, port in WEBVIS_PORTS.items():
        try:
            sock = socket.create_connection(("localhost", port), timeout=3)
            sock.close()
            alive = True
        except Exception:
            alive = False

        c.check(
            alive,
            f"{name} webvis (:{port}) is responding",
            f"{name} webvis (:{port}) is not responding",
        )

    # ── Phase 3: Metric Verification ───────────────────────────────────
    print("\n== Phase 3: Metric Verification ==")

    # 3a. Pipeline presence in aggregated_metrics
    print("  -- pipeline presence --")
    found_pids = set()
    try:
        data = query_prometheus(
            args.prometheus_url,
            'aggregated_metrics{metric="process_time_ms"}',
        )
        for r in data["data"]["result"]:
            pid = r["metric"].get("pipeline_id", "")
            if pid:
                found_pids.add(pid)
    except Exception as e:
        c.fail(f"could not query aggregated_metrics: {e}")

    for pid in PIPELINE_IDS:
        c.check(
            pid in found_pids,
            f"pipeline_id '{pid}' found in aggregated_metrics",
            f"pipeline_id '{pid}' NOT found in aggregated_metrics (retry after 30-60s if pipelines just started)",
        )

    # 3b. Per-filter class names
    print("  -- per-filter classes --")
    for pid, expected_classes in EXPECTED_FILTERS.items():
        try:
            data = query_prometheus(
                args.prometheus_url,
                f'openfilter_process_time_ms{{pipeline_id="{pid}"}}',
            )
            actual_classes = {
                r["metric"].get("filter_name", "")
                for r in data["data"]["result"]
            }
            actual_classes.discard("")
            missing = expected_classes - actual_classes
            c.check(
                not missing,
                f"{pid}: all expected filter classes present ({', '.join(sorted(actual_classes))})",
                f"{pid}: missing filter classes {missing} (found: {actual_classes or 'none'}). Retry after 60s if pipelines just started.",
            )
        except Exception as e:
            c.fail(f"{pid}: could not query per-filter metrics: {e}")

    # 3c. FPS > 0
    print("  -- fps check --")
    try:
        data = query_prometheus(
            args.prometheus_url,
            'aggregated_metrics{metric="fps"}',
        )
        fps_by_pid = {}
        for r in data["data"]["result"]:
            pid = r["metric"].get("pipeline_id", "")
            val = float(r["value"][1])
            if pid:
                fps_by_pid[pid] = val

        for pid in PIPELINE_IDS:
            fps = fps_by_pid.get(pid)
            if fps is not None and fps > 0:
                c.ok(f"{pid}: fps = {fps:.2f}")
            elif fps is not None:
                c.fail(f"{pid}: fps = {fps:.2f} (expected > 0)")
            else:
                c.fail(f"{pid}: no fps metric found (retry after 30-60s)")
    except Exception as e:
        c.fail(f"could not query fps metrics: {e}")

    # ── Phase 4: Frame Flow ────────────────────────────────────────────
    print("\n== Phase 4: Frame Flow ==")

    for name, port in WEBVIS_PORTS.items():
        data = read_mjpeg_bytes("localhost", port)
        if data is None:
            c.fail(f"{name} (:{port}): could not connect to MJPEG stream")
            continue

        has_boundary = b"--frame" in data
        has_jpeg_soi = b"\xff\xd8" in data
        c.check(
            has_boundary and has_jpeg_soi,
            f"{name} (:{port}): MJPEG frames detected",
            f"{name} (:{port}): no MJPEG frames found (boundary={has_boundary}, jpeg_soi={has_jpeg_soi})",
        )

    # ── Summary ────────────────────────────────────────────────────────
    total = c.passed + c.failed
    print(f"\n{'=' * 18}")
    print(f"Results: {c.passed}/{total} passed, {c.failed} failed")
    sys.exit(0 if c.failed == 0 else 1)


if __name__ == "__main__":
    main()
