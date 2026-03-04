#!/usr/bin/env python3
"""
Verify that the Slack alerting pipeline is correctly configured and operational.

Checks:
  1. Alertmanager health
  2. Slack webhook is configured (not a placeholder)
  3. Expected receivers are present
  4. Alert rules exist in Prometheus
  5. Prometheus can reach Alertmanager
  6. (Optional) Send a test alert to verify end-to-end delivery

Usage:
    python verify_alerts.py
    python verify_alerts.py --send-test-alert
    python verify_alerts.py --resolve-test-alert
    python verify_alerts.py --alertmanager-url http://myhost:9093
"""
import argparse
import json
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

EXPECTED_ALERT_NAMES = [
    "PipelineDown",
    "CameraDisconnected",
    "DiskCritical",
    "GPUUnavailable",
]

PLACEHOLDER_PATTERNS = [
    "NOT_CONFIGURED",
    "REPLACE_ME",
    "SLACK_WEBHOOK_PLACEHOLDER",
    "YOUR/WEBHOOK/URL",
]

EXPECTED_RECEIVERS = ["slack-default", "slack-critical"]


def http_get_json(url):
    with urllib.request.urlopen(url, timeout=10) as resp:
        return json.loads(resp.read())


def check_alertmanager_health(base_url):
    """Check 1: Alertmanager is reachable and healthy."""
    print("== Alertmanager health ==")
    try:
        url = f"{base_url}/-/healthy"
        with urllib.request.urlopen(url, timeout=5) as resp:
            if resp.status == 200:
                print("  PASS: Alertmanager is healthy")
                return True
    except Exception as e:
        pass
    print("  FAIL: Alertmanager is not reachable")
    return False


def check_slack_webhook(base_url):
    """Check 2: Slack webhook URL is configured (not a placeholder).

    Alertmanager masks slack_api_url as <secret> in its API, so we check
    the host SLACK_WEBHOOK_URL env var (which is what Docker Compose injects)
    and fall back to reading the rendered config from inside the container.
    """
    print("\n== Slack webhook configuration ==")

    # Strategy 1: Check the host environment variable
    import os
    host_url = os.environ.get("SLACK_WEBHOOK_URL", "")
    if host_url:
        for pattern in PLACEHOLDER_PATTERNS:
            if pattern in host_url:
                print(f"  FAIL: SLACK_WEBHOOK_URL contains placeholder '{pattern}'")
                print("        Update SLACK_WEBHOOK_URL with a real webhook URL and restart the stack")
                return False
        print("  PASS: SLACK_WEBHOOK_URL is set and not a placeholder")
        return True

    # Strategy 2: Try reading the rendered config from the container
    import subprocess
    try:
        result = subprocess.run(
            ["docker", "exec", "monitoring-alertmanager-1", "cat", "/tmp/alertmanager.yml"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            config_str = result.stdout
            for pattern in PLACEHOLDER_PATTERNS:
                if pattern in config_str:
                    print(f"  FAIL: Slack webhook contains placeholder '{pattern}'")
                    print("        Set SLACK_WEBHOOK_URL env var and restart the stack")
                    return False
            if "slack_api_url" in config_str:
                print("  PASS: Slack webhook URL is configured (verified via container config)")
                return True
    except Exception:
        pass

    # Strategy 3: If we can't determine, warn
    print("  FAIL: SLACK_WEBHOOK_URL env var is not set")
    print("        Set it before starting the stack: export SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...")
    return False


def check_receivers(base_url):
    """Check 3: Expected Slack receivers are present in config."""
    print("\n== Alertmanager receivers ==")
    try:
        data = http_get_json(f"{base_url}/api/v2/receivers")
        receiver_names = [r.get("name", "") for r in data]

        all_found = True
        for name in EXPECTED_RECEIVERS:
            if name in receiver_names:
                print(f"  PASS: Receiver '{name}' is present")
            else:
                print(f"  FAIL: Receiver '{name}' not found")
                all_found = False
        return all_found
    except Exception as e:
        print(f"  FAIL: Could not query receivers: {e}")
        return False


def check_alert_rules(prom_url):
    """Check 4: All expected alert rules exist in Prometheus."""
    print("\n== Prometheus alert rules ==")
    try:
        data = http_get_json(f"{prom_url}/api/v1/rules")
        rules_found = set()
        for group in data.get("data", {}).get("groups", []):
            for rule in group.get("rules", []):
                rules_found.add(rule["name"])

        all_found = True
        for name in EXPECTED_ALERT_NAMES:
            if name in rules_found:
                print(f"  PASS: Alert rule '{name}' exists")
            else:
                print(f"  FAIL: Alert rule '{name}' not found")
                all_found = False
        return all_found
    except Exception as e:
        print(f"  FAIL: Could not query Prometheus rules: {e}")
        return False


def check_alertmanager_discovery(prom_url):
    """Check 5: Prometheus has discovered Alertmanager as a target."""
    print("\n== Prometheus -> Alertmanager connectivity ==")
    try:
        data = http_get_json(f"{prom_url}/api/v1/alertmanagers")
        active = data.get("data", {}).get("activeAlertmanagers", [])
        if active:
            for am in active:
                print(f"  PASS: Alertmanager target discovered: {am.get('url', 'unknown')}")
            return True
        else:
            print("  FAIL: No active Alertmanager targets found in Prometheus")
            print("        Check prometheus.yaml alerting config")
            return False
    except Exception as e:
        print(f"  FAIL: Could not query Alertmanager discovery: {e}")
        return False


TEST_ALERT_LABELS = {
    "alertname": "TestAlert",
    "severity": "warning",
    "pipeline_instance_id": "verify-alerts-test",
}


def send_test_alert(am_url):
    """Check 6 (optional): Send a test alert to Alertmanager.

    Sets endsAt 24 hours in the future so the alert persists until manually
    resolved (via --resolve-test-alert) instead of vanishing after 5 minutes.
    """
    print("\n== Sending test alert ==")
    ends_at = (datetime.now(timezone.utc) + timedelta(hours=24)).strftime(
        "%Y-%m-%dT%H:%M:%S.000Z"
    )
    alert = [
        {
            "labels": TEST_ALERT_LABELS,
            "annotations": {
                "summary": "Test alert from verify_alerts.py",
                "description": "This is a test alert to verify Slack integration is working. "
                "Run 'make resolve-test-alert' or pass --resolve-test-alert to resolve it.",
            },
            "endsAt": ends_at,
        }
    ]
    try:
        payload = json.dumps(alert).encode("utf-8")
        req = urllib.request.Request(
            f"{am_url}/api/v2/alerts",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status == 200:
                print("  PASS: Test alert posted to Alertmanager")
                print("        Check your Slack channel for the alert")
                print(f"        Alert will persist until resolved (endsAt: {ends_at})")
                print("        To resolve: python verify_alerts.py --resolve-test-alert")
                return True
            else:
                print(f"  FAIL: Unexpected status {resp.status}")
                return False
    except Exception as e:
        print(f"  FAIL: Could not post test alert: {e}")
        return False


def resolve_test_alert(am_url):
    """Resolve the TestAlert by re-sending it with endsAt set to now."""
    print("== Resolving test alert ==")
    ends_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    alert = [
        {
            "labels": TEST_ALERT_LABELS,
            "annotations": {
                "summary": "Test alert from verify_alerts.py (resolved)",
                "description": "Manually resolved via --resolve-test-alert.",
            },
            "endsAt": ends_at,
        }
    ]
    try:
        payload = json.dumps(alert).encode("utf-8")
        req = urllib.request.Request(
            f"{am_url}/api/v2/alerts",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status == 200:
                print("  PASS: Resolve signal sent to Alertmanager")
                print("        The alert should clear from Slack shortly")
                return True
            else:
                print(f"  FAIL: Unexpected status {resp.status}")
                return False
    except Exception as e:
        print(f"  FAIL: Could not resolve test alert: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Verify Slack alerting pipeline is correctly configured"
    )
    parser.add_argument("--prometheus-url", default="http://localhost:9090")
    parser.add_argument("--alertmanager-url", default="http://localhost:9093")
    parser.add_argument(
        "--send-test-alert",
        action="store_true",
        help="Send a test alert to verify end-to-end Slack delivery",
    )
    parser.add_argument(
        "--resolve-test-alert",
        action="store_true",
        help="Resolve a previously sent test alert",
    )
    args = parser.parse_args()

    # Standalone resolve mode: just resolve and exit
    if args.resolve_test_alert:
        ok = resolve_test_alert(args.alertmanager_url)
        sys.exit(0 if ok else 1)

    passed = 0
    failed = 0

    checks = [
        lambda: check_alertmanager_health(args.alertmanager_url),
        lambda: check_slack_webhook(args.alertmanager_url),
        lambda: check_receivers(args.alertmanager_url),
        lambda: check_alert_rules(args.prometheus_url),
        lambda: check_alertmanager_discovery(args.prometheus_url),
    ]

    if args.send_test_alert:
        checks.append(lambda: send_test_alert(args.alertmanager_url))

    for check in checks:
        if check():
            passed += 1
        else:
            failed += 1

    total = passed + failed
    print(f"\n{'=' * 40}")
    print(f"Results: {passed}/{total} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
