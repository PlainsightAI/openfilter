#!/usr/bin/env python3
"""
Verify that health metrics from a running pipeline have landed in Prometheus
and that alert rules are evaluating correctly.

Usage:
    python verify_metrics.py                 # Run all checks
    python verify_metrics.py --prometheus-url http://myhost:9090
"""
import argparse
import json
import sys
import urllib.request

HEALTH_METRICS = [
    "openfilter_camera_connected",
    "openfilter_disk_usage_percent",
    "openfilter_ram_usage_percent",
    "openfilter_gpu_accessible",
    "openfilter_gpu_usage_percent",
    "openfilter_filter_time_in",
    "openfilter_filter_time_out",
    "openfilter_process_time_ms",
    "openfilter_frame_total_time_ms",
    "openfilter_frame_avg_time_ms",
    "openfilter_frame_std_time_ms",
]

ALERT_NAMES = ["PipelineDown", "CameraDisconnected", "DiskCritical", "GPUUnavailable"]


def query_prometheus(base_url, promql):
    url = f"{base_url}/api/v1/query?query={urllib.parse.quote(promql)}"
    with urllib.request.urlopen(url, timeout=5) as resp:
        return json.loads(resp.read())


def check_health(base_url):
    url = f"{base_url}/-/healthy"
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            return resp.status == 200
    except Exception:
        return False


def main():
    import urllib.parse  # noqa: ensure available

    parser = argparse.ArgumentParser(description="Verify monitoring stack metrics and alerts")
    parser.add_argument("--prometheus-url", default="http://localhost:9090")
    parser.add_argument("--alertmanager-url", default="http://localhost:9093")
    args = parser.parse_args()

    passed = 0
    failed = 0

    # --- Prometheus health ---
    print("== Prometheus health ==")
    if check_health(args.prometheus_url):
        print("  PASS: Prometheus is healthy")
        passed += 1
    else:
        print("  FAIL: Prometheus is not reachable")
        failed += 1

    # --- Health metrics ---
    print("\n== Health metrics in Prometheus ==")
    for metric in HEALTH_METRICS:
        try:
            data = query_prometheus(args.prometheus_url, metric)
            results = data["data"]["result"]
            if not results:
                print(f"  FAIL: {metric} — no data points")
                failed += 1
                continue

            for r in results:
                value = r["value"][1]
                pid = r["metric"].get("pipeline_instance_id", "MISSING")
                print(f"  PASS: {metric} = {value}  (pipeline_instance_id={pid})")

            # Verify pipeline_instance_id label exists
            if any("pipeline_instance_id" not in r["metric"] for r in results):
                print(f"  FAIL: {metric} — missing pipeline_instance_id label")
                failed += 1
            else:
                passed += 1

        except Exception as e:
            print(f"  FAIL: {metric} — {e}")
            failed += 1

    # --- Alert rules ---
    print("\n== Alert rule states ==")
    try:
        url = f"{args.prometheus_url}/api/v1/rules"
        with urllib.request.urlopen(url, timeout=5) as resp:
            data = json.loads(resp.read())

        rules_found = {}
        for group in data["data"]["groups"]:
            for rule in group["rules"]:
                rules_found[rule["name"]] = rule["state"]
                alerts_count = len(rule.get("alerts", []))
                print(f"  {rule['name']}: state={rule['state']}  (active_alerts={alerts_count})")

        for name in ALERT_NAMES:
            if name in rules_found:
                passed += 1
            else:
                print(f"  FAIL: alert rule {name} not found")
                failed += 1

    except Exception as e:
        print(f"  FAIL: could not query alert rules — {e}")
        failed += 1

    # --- Alertmanager ---
    print("\n== Alertmanager alerts ==")
    try:
        url = f"{args.alertmanager_url}/api/v2/alerts"
        with urllib.request.urlopen(url, timeout=5) as resp:
            alerts = json.loads(resp.read())

        if not alerts:
            print("  (no alerts currently firing)")
        else:
            for a in alerts:
                labels = a.get("labels", {})
                status = a.get("status", {}).get("state", "unknown")
                print(f"  ALERT: {labels.get('alertname')}  severity={labels.get('severity')}  status={status}  pipeline={labels.get('pipeline_instance_id', 'n/a')}")
        passed += 1

    except Exception as e:
        print(f"  FAIL: could not query Alertmanager — {e}")
        failed += 1

    # --- Summary ---
    total = passed + failed
    print(f"\n{'=' * 40}")
    print(f"Results: {passed}/{total} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
