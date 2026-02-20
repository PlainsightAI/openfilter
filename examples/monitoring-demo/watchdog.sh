#!/bin/bash
# Watchdog: checks pipeline + monitoring stack every 15 minutes for 5 hours.
# Auto-restarts pipeline if it dies. Logs to /tmp/monitoring-watchdog.log.

LOG=/tmp/monitoring-watchdog.log
PIPELINE_LOG=/tmp/monitoring-demo-pipeline.log
DURATION=18000
EXPORT_INTERVAL=5000
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CHECKS=20  # 5 hours / 15 min = 20 checks

echo "$(date) [watchdog] Starting. $CHECKS checks, 15 min apart." | tee -a "$LOG"

for i in $(seq 1 $CHECKS); do
    sleep 900  # 15 minutes

    echo "" | tee -a "$LOG"
    echo "$(date) [watchdog] Check $i/$CHECKS" | tee -a "$LOG"

    # Check pipeline
    if pgrep -f "run_pipeline.py" > /dev/null; then
        PID=$(pgrep -f "run_pipeline.py" | head -1)
        echo "  Pipeline: running (PID=$PID)" | tee -a "$LOG"
    else
        echo "  Pipeline: DEAD — restarting..." | tee -a "$LOG"
        cd "$SCRIPT_DIR"
        source /Users/navarmn/.virtualenvs/plainsight/bin/activate
        nohup python run_pipeline.py --duration $DURATION --export-interval $EXPORT_INTERVAL >> "$PIPELINE_LOG" 2>&1 &
        echo "  Pipeline restarted (PID=$!)" | tee -a "$LOG"
        sleep 90  # wait for metrics to appear
    fi

    # Check containers
    for svc in otel-collector prometheus alertmanager grafana; do
        STATUS=$(docker inspect --format='{{.State.Status}}' "monitoring-${svc}-1" 2>/dev/null || echo "missing")
        if [ "$STATUS" = "running" ]; then
            echo "  $svc: OK" | tee -a "$LOG"
        else
            echo "  $svc: $STATUS — restarting..." | tee -a "$LOG"
            docker restart "monitoring-${svc}-1" 2>/dev/null
        fi
    done

    # Check Prometheus has data
    RESULT=$(curl -sf 'http://localhost:9090/api/v1/query?query=openfilter_disk_usage_percent' 2>/dev/null | python3 -c "import json,sys; d=json.load(sys.stdin); print(len(d['data']['result']))" 2>/dev/null || echo "0")
    if [ "$RESULT" -gt 0 ]; then
        echo "  Metrics in Prometheus: OK ($RESULT series)" | tee -a "$LOG"
    else
        echo "  Metrics in Prometheus: MISSING" | tee -a "$LOG"
    fi

    # Check alerts
    ALERTS=$(curl -sf 'http://localhost:9090/api/v1/rules' 2>/dev/null | python3 -c "
import json,sys
d=json.load(sys.stdin)
for g in d['data']['groups']:
    for r in g['rules']:
        print(f'    {r[\"name\"]}: {r[\"state\"]}')
" 2>/dev/null || echo "    (unavailable)")
    echo "  Alerts:" | tee -a "$LOG"
    echo "$ALERTS" | tee -a "$LOG"
done

echo "" | tee -a "$LOG"
echo "$(date) [watchdog] Done. 5 hours complete." | tee -a "$LOG"
