# Monitoring Demo

Run an OpenFilter pipeline and observe its health metrics in Prometheus, Grafana, and Alertmanager.

## What It Does

A minimal `VideoIn` pipeline reads a looping video file and exports five health metrics via OpenTelemetry to the monitoring stack:

| Metric | Type | Description |
|--------|------|-------------|
| `openfilter_camera_connected` | Gauge (0/1) | Video source delivering frames |
| `openfilter_disk_usage_percent` | Gauge (0-100) | Host disk usage |
| `openfilter_ram_usage_percent` | Gauge (0-100) | Host RAM usage |
| `openfilter_gpu_accessible` | Gauge (0/1) | CUDA GPU available |
| `openfilter_gpu_usage_percent` | Gauge (0-100) | GPU utilization (nvidia-smi) |
| `openfilter_filter_time_in` | Gauge (epoch s) | Timestamp when filter started processing (per filter) |
| `openfilter_filter_time_out` | Gauge (epoch s) | Timestamp when filter finished processing (per filter) |
| `openfilter_process_time_ms` | Gauge (EMA ms) | Per-filter processing time (per filter) |
| `openfilter_frame_total_time_ms` | Gauge (EMA ms) | Sum of all filters' durations (last filter only) |
| `openfilter_frame_avg_time_ms` | Gauge (EMA ms) | Average duration across filters (last filter only) |
| `openfilter_frame_std_time_ms` | Gauge (EMA ms) | Std dev of durations across filters (last filter only) |

```
Pipeline (Python)              Docker Monitoring Stack
================              =======================
                   OTLP gRPC
VideoIn ──────────────────────> OTEL Collector (:4317)
  │                                   │
  └─ FiltersToQueue (sink)            │ Prometheus exporter (:8889)
                                      ▼
                                Prometheus (:9090) ──> Alert Rules
                                      │                     │
                                      ▼                     ▼
                                Grafana (:3000)       Alertmanager (:9093)
```

## Prerequisites

- Docker with Compose v2
- Python virtualenv with `openfilter` installed
- Video file at `examples/hello-world/example_video.mp4` (included in repo)

## Quick Start

```bash
cd examples/monitoring-demo

# 1. Start the monitoring stack
make stack-up

# 2. Run the pipeline (runs for 120s, Ctrl+C to stop early)
make run

# 3. In another terminal, verify metrics after ~30s
make verify

# 4. Open Grafana to visualize
#    http://localhost:3000  (admin / admin)

# 5. Tear down
make clean
```

Or all at once:

```bash
make all    # starts stack, then runs pipeline
```

## Step-by-Step

### 1. Start the monitoring stack

```bash
make stack-up
```

This starts four containers:

| Service | Port | URL |
|---------|------|-----|
| OTEL Collector (gRPC) | 4317 | -- |
| OTEL Collector (Prometheus exporter) | 8889 | http://localhost:8889/metrics |
| Prometheus | 9090 | http://localhost:9090 |
| Alertmanager | 9093 | http://localhost:9093 |
| Grafana | 3000 | http://localhost:3000 (admin/admin) |

### 2. Run the pipeline

```bash
make run
```

This runs `run_pipeline.py` which:
- Reads `examples/hello-world/example_video.mp4` in a loop at 5 fps
- Exports metrics via OTLP gRPC to `localhost:4317` every 10s
- Exits after 120s (or Ctrl+C)

Options:

```bash
# Custom video, shorter run
python run_pipeline.py --source /path/to/video.mp4 --duration 60

# Console exporter (no Docker stack needed, prints metrics to stdout)
python run_pipeline.py --exporter console --duration 30

# Faster export interval
python run_pipeline.py --export-interval 5000
```

### 3. Verify metrics

After the pipeline has run for at least 30 seconds:

```bash
make verify
```

Sample output:

```
== Prometheus health ==
  PASS: Prometheus is healthy

== Health metrics in Prometheus ==
  PASS: openfilter_camera_connected = 1  (pipeline_instance_id=...)
  PASS: openfilter_disk_usage_percent = 48.48  (pipeline_instance_id=...)
  PASS: openfilter_ram_usage_percent = 73.5  (pipeline_instance_id=...)
  PASS: openfilter_gpu_accessible = 0  (pipeline_instance_id=...)
  PASS: openfilter_gpu_usage_percent = 0  (pipeline_instance_id=...)

== Alert rule states ==
  PipelineDown: state=inactive  (active_alerts=0)
  CameraDisconnected: state=inactive  (active_alerts=0)
  DiskCritical: state=inactive  (active_alerts=0)
  GPUUnavailable: state=firing  (active_alerts=2)

== Alertmanager alerts ==
  ALERT: GPUUnavailable  severity=critical  status=active  pipeline=...

Results: 11/11 passed, 0 failed
```

### 4. Visualize in Grafana

1. Open http://localhost:3000 (login: admin / admin)
2. Go to Explore (compass icon)
3. Prometheus datasource is pre-configured
4. Try these PromQL queries:

| Panel | Query |
|-------|-------|
| Disk Usage | `openfilter_disk_usage_percent` |
| RAM Usage | `openfilter_ram_usage_percent` |
| Camera Status | `openfilter_camera_connected` |
| GPU Status | `openfilter_gpu_accessible` |
| GPU Utilization | `openfilter_gpu_usage_percent` |
| Pipeline FPS | `videoin_fps` |
| Filter Process Time | `openfilter_process_time_ms` |
| Frame Total Time | `openfilter_frame_total_time_ms` |
| Frame Avg Time | `openfilter_frame_avg_time_ms` |
| Frame Std Dev | `openfilter_frame_std_time_ms` |

### 5. Tear down

```bash
make clean
```

## Alert Rules

Four alert rules are pre-configured in `docker/monitoring/alert-rules.yaml`:

| Alert | Condition | For | Severity |
|-------|-----------|-----|----------|
| `PipelineDown` | No metrics received in 60s | 30s | critical |
| `CameraDisconnected` | `camera_connected == 0` | 30s | critical |
| `DiskCritical` | `disk_usage_percent > 90` | 1m | warning |
| `GPUUnavailable` | `gpu_accessible == 0` | 30s | critical |

When `PipelineDown` fires, it suppresses the other three alerts for the same pipeline (inhibition rule).

## Expected Results on macOS (No GPU)

| Alert | State | Why |
|-------|-------|-----|
| PipelineDown | inactive | Metrics arriving normally |
| CameraDisconnected | inactive | Video file delivers frames (camera_connected=1) |
| DiskCritical | inactive | Disk typically well below 90% |
| GPUUnavailable | **firing** | No CUDA GPU on Mac (gpu_accessible=0) |

## Troubleshooting

**No metrics appearing after 30s?**
- Check `make stack-health` -- all services should show OK
- Check that the pipeline is running (`ps aux | grep run_pipeline`)
- Check OTEL collector is receiving data: `curl http://localhost:8889/metrics | grep openfilter`

**Pipeline crashes with "must specify at least one output"?**
- VideoIn requires a downstream filter. The demo script handles this with FiltersToQueue.

**Pipeline crashes with "Source is invalid"?**
- The video file path must be absolute. The script resolves it automatically.
- On macOS, Python `multiprocessing.spawn` requires a script file (not stdin/heredoc).

## Files

```
examples/monitoring-demo/
  Makefile            Make targets for the full workflow
  run_pipeline.py     Pipeline script with OTLP export
  verify_metrics.py   Metric and alert verification script
  README.md           This file
```

Monitoring stack config lives in `docker/monitoring/`:

```
docker/monitoring/
  docker-compose.monitoring.yaml   Container definitions
  otel-collector-config.yaml       OTLP -> Prometheus pipeline
  prometheus.yaml                  Scrape config + alerting
  alert-rules.yaml                 4 health alert rules
  alertmanager.yaml                Routing + Slack receivers
  grafana-datasources.yaml         Auto-provisioned Prometheus datasource
```
