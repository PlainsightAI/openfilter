# Monitoring Demo

Run four OpenFilter pipelines simultaneously and observe their metrics in Prometheus, Grafana, and Alertmanager.

## Quick Start

```bash
cd examples/monitoring-demo

# Build the image + start all 4 pipelines and the monitoring stack
make pipelines-up

# Wait ~70 seconds for the first metrics export, then open:
#   Grafana:    http://localhost:3000  (admin / admin)
#   Prometheus: http://localhost:9090
#   P1 video:   http://localhost:8001
#   P2 video:   http://localhost:8002
#   P3 video:   http://localhost:8003
#   P4 video:   http://localhost:8004

# Verify all metrics landed in Prometheus
make pipelines-verify

# Tear down everything
make pipelines-down
```

## The Four Pipelines

All pipelines read the same looping video file at 5 fps. They run in parallel and each exports metrics independently to the same monitoring stack. Each represents a different real-world topology pattern.

### P1: transform-chain (linear)

```mermaid
flowchart LR
    A["VideoIn"] --> B["GrayscaleFilter"]
    B --> C["ResizeFilter"]
    C --> D["TimingFilter"]
    D --> E["Webvis"]
```

The simplest topology. Frames flow through a single chain of transforms, one after the other. Each filter processes exactly one frame at a time before passing it downstream.

**What to look for:** All filters show nearly identical FPS (they are all in the same chain, so if one slows down they all slow down). Per-filter process times are additive: the end-to-end latency roughly equals the sum of individual processing times plus ZMQ transmission overhead.

**Webvis:** http://localhost:8001 (grayscale + resized video)

### P2: fan-out

```mermaid
flowchart LR
    A["VideoIn"] --> B["GrayscaleFilter"]
    A --> C["ResizeFilter"]
    B --> D["TimingFilter_A"]
    C --> E["TimingFilter_B"]
    D --> F["Webvis"]
    E --> F
```

One source feeding two independent branches simultaneously. The same frame goes to both branches at the same time. Each branch processes independently at its own speed. The sink (Webvis) merges them back, receiving frames from both.

**What to look for:** VideoIn FPS matches both branches (it broadcasts to both). TimingFilter_A and TimingFilter_B have separate process-time series and separate end-to-end latency measurements because they are independent sinks for their branch. The two branches may drift slightly in frame count if one is slower.

**Webvis:** http://localhost:8002 (shows both grayscale and resized topics)

### P3: diamond

```mermaid
flowchart LR
    A["VideoIn"] --> B["GrayscaleFilter"]
    A --> C["StatsFilter"]
    B --> D["TimingFilter"]
    C --> D
    D --> E["Webvis"]
```

Fan-out at the source and fan-in at the merge point. Both branches process in parallel and TimingFilter waits for both to arrive before emitting downstream. This is the classic diamond topology used when you need to combine the results of two different analyses of the same frame.

**What to look for:** End-to-end latency on the right panel reflects the *critical path*, meaning the slower of the two branches determines the overall pipeline speed. If GrayscaleFilter takes 3ms and StatsFilter takes 10ms, the total latency includes the 10ms wait even though Grayscale finished earlier. The per-filter process times on the left show both branches separately.

**Webvis:** http://localhost:8003

### P4: diamond-same-class

```mermaid
flowchart LR
    A["VideoIn"] --> B["SlowPassthrough\n(50ms, id=p4_slow_b1)"]
    A --> C["SlowPassthrough\n(80ms, id=p4_slow_b2)"]
    B --> D["TimingFilter"]
    C --> D
    D --> E["Webvis"]
```

Same topology as P3 but both parallel branches use the *same Python class* (`SlowPassthrough`) with different `FILTER_ID` values and different artificial sleep durations. This pipeline was created to expose and verify fixes for two bugs:

**Bug 1 (metric label collision):** When two filters share the same class name, they used to collide in Prometheus as a single metric series. After the fix, `p4_slow_b1` and `p4_slow_b2` appear as two separate lines in the Per-Filter Process Time panel.

**Bug 2 (wrong fan-in aggregate timing):** Before the fix, the end-to-end latency for the merged pipeline was measured from the *first* branch to arrive (50ms branch), not the slowest (80ms branch). After the fix, the total latency correctly reflects the critical path. You can verify this: P4's end-to-end latency (~280ms) is about 80ms higher than P1/P2/P3 (~200ms), exactly matching the slower branch's sleep.

**Webvis:** http://localhost:8004

## Grafana Dashboard

The dashboard is auto-provisioned at startup. Open http://localhost:3000 (admin / admin) and select **OpenFilter Pipeline Monitor**.

### Filtering by Pipeline

The **Pipeline** dropdown at the top of the dashboard controls which pipeline(s) are shown. It defaults to **All**. To focus on one pipeline:

1. Click the **Pipeline** dropdown (top left of the dashboard)
2. Uncheck **All**
3. Select a single pipeline (e.g. `diamond-same-class`)

All panels update immediately to show only that pipeline's data. The variable is multi-select, so you can compare two pipelines by selecting both.

### Dashboard Sections

#### Overview (top row)

Quick health summary. Shows active pipeline count, total FPS across all filters, camera connection status, disk usage, RAM usage, and GPU accessibility. On macOS, GPU will always show NO GPU (expected, no nvidia-smi).

#### Throughput

**FPS per Filter:** One line per filter instance. All filters in the same pipeline should hover at the same value (~5 fps in this demo). A line that drops below the others means that filter is the bottleneck.

**Input / Output Latency:** `lat_in` is how long a frame waits in the ZMQ queue before this filter picks it up. `lat_out` is the time to emit the frame downstream. High `lat_in` means upstream is pushing faster than this filter can consume.

**Frames Processed / Megapixels:** Cumulative counters that should increase at the same slope across all filters in the same pipeline. A filter with a slower slope is not keeping up with the frame rate.

#### End-to-End Timing

This section has two panels that measure different things.

**Left panel: Per-Filter Process Time (ms, EMA)**

The time each filter's `process()` function took, smoothed with an exponential moving average. This is the time spent *inside* the filter doing actual work. It does not include time waiting in queues or ZMQ transmission.

In P4, both `SlowPassthrough` instances (`p4_slow_b1` at ~50ms, `p4_slow_b2` at ~80ms) appear as separate lines. Without the Bug 1 fix they would have collapsed into a single line.

**Right panel: End-to-End Latency (ms, EMA)**

The full wall-clock time a frame takes from entering the source filter to exiting the sink (Webvis). This is measured at the sink, not computed by adding up the left panel values.

It is larger than the sum of per-filter process times because it also includes ZMQ transmission time between filters, queue wait times, and OS scheduling overhead. One series per pipeline (because there is one sink per pipeline).

For fan-in topologies (P3 diamond, P4 diamond-same-class), the total time reflects the *critical path*: the end-to-end latency is determined by the slowest parallel branch, not the first one to arrive.

`total` = full frame journey from source to sink.
`avg/stage` = mean of all per-filter process times for that pipeline.
`std/stage` = standard deviation across filter stages (higher means uneven stage times).

**How to compare them:** Select a single pipeline from the Pipeline dropdown. The left panel shows which individual filter is the bottleneck. The right panel shows the resulting impact on end-to-end latency, including all transmission overhead.

#### Resource Usage

**CPU % per Filter:** Per-process CPU usage. In this demo (5 fps, simple transforms) it stays low. VideoIn is typically the highest due to video decoding. If a filter hits near 100%, it cannot keep up with the configured frame rate.

**Memory (GB) per Filter:** RSS memory footprint. Slow steady growth over time suggests a memory leak in that filter.

#### System Health

**Uptime:** How long each filter has been running, computed as `frames_processed / fps`. All lines should grow at the same rate. A reset to zero means the filter process restarted.

**Firing Alerts:** Active Prometheus alerts. On macOS the `GPUUnavailable` alert will always be firing (no nvidia-smi available). `PipelineDown` fires if any pipeline stops sending metrics for 90 seconds.

## Metrics Reference

### Per-Filter Metrics

These are reported by every filter independently. All have labels: `filter_name`, `filter_id`, `pipeline_id`.

| Prometheus Name | Description |
|-----------------|-------------|
| `{filtername}_fps` | Frames per second |
| `{filtername}_cpu` | CPU usage percent |
| `{filtername}_mem` | Memory in GB |
| `{filtername}_lat_in` | Input queue wait time (ms) |
| `{filtername}_lat_out` | Output emit time (ms) |
| `{filtername}_frame_count_total` | Cumulative frames processed |
| `{filtername}_megapx_count_total` | Cumulative megapixels processed |
| `{filtername}_uptime_count_total` | Frames processed since startup (divide by fps for seconds) |

Note: Prometheus lowercases all metric names. `GrayscaleFilter` becomes `grayscalefilter`, `SlowPassthrough` becomes `slowpassthrough`, etc.

### Shared Timing Metrics

These use the `openfilter_` prefix and are emitted by the filter runtime for all filters.

| Metric | Reported By | Description |
|--------|-------------|-------------|
| `openfilter_process_time_ms` | Every filter | process() duration, EMA-smoothed |
| `openfilter_filter_time_in` | Every filter | Unix timestamp when frame entered the filter |
| `openfilter_filter_time_out` | Every filter | Unix timestamp when frame left the filter |
| `openfilter_frame_total_time_ms` | Sink only | Full pipeline wall-clock latency, EMA-smoothed |
| `openfilter_frame_avg_time_ms` | Sink only | Mean per-stage process time, EMA-smoothed |
| `openfilter_frame_std_time_ms` | Sink only | Std dev of per-stage process times, EMA-smoothed |

### System Health Metrics

| Metric | Description |
|--------|-------------|
| `openfilter_camera_connected` | 1 = source delivering frames, 0 = disconnected |
| `openfilter_disk_usage_percent` | Host disk usage (0-100) |
| `openfilter_ram_usage_percent` | Host RAM usage (0-100) |
| `openfilter_gpu_accessible` | 1 = CUDA GPU found, 0 = not found |
| `openfilter_gpu_usage_percent` | GPU utilization from nvidia-smi |

## Alert Rules

Pre-configured in `docker/monitoring/alert-rules.yaml`. When `PipelineDown` fires it suppresses all other alerts for the same pipeline.

| Alert | Condition | For | Severity |
|-------|-----------|-----|----------|
| `PipelineDown` | No metrics received for 60s | 30s | critical |
| `CameraDisconnected` | `camera_connected == 0` | 30s | critical |
| `DiskCritical` | `disk_usage_percent > 90` | 1m | warning |
| `GPUUnavailable` | `gpu_accessible == 0` | 30s | critical |
| `DiskCriticalTest` | `disk_usage_percent > 10` | 15s | warning (test only) |

To receive Slack alerts, export `SLACK_WEBHOOK_URL` before running `make pipelines-up`.

## Services and Ports

| Service | Port | URL |
|---------|------|-----|
| Grafana | 3000 | http://localhost:3000 (admin / admin) |
| Prometheus | 9090 | http://localhost:9090 |
| Alertmanager | 9093 | http://localhost:9093 |
| OTEL Collector gRPC | 4317 | (internal) |
| OTEL Collector Prometheus exporter | 8889 | http://localhost:8889/metrics |
| P1 Webvis (transform-chain) | 8001 | http://localhost:8001 |
| P2 Webvis (fan-out) | 8002 | http://localhost:8002 |
| P3 Webvis (diamond) | 8003 | http://localhost:8003 |
| P4 Webvis (diamond-same-class) | 8004 | http://localhost:8004 |

## Architecture

```mermaid
flowchart LR
    P1["P1 filters"] -->|OTLP gRPC| OC["OTEL Collector\n(:4317)"]
    P2["P2 filters"] -->|OTLP gRPC| OC
    P3["P3 filters"] -->|OTLP gRPC| OC
    P4["P4 filters"] -->|OTLP gRPC| OC
    OC -->|Prometheus exporter :8889| PR["Prometheus\n(:9090)"]
    PR --> GR["Grafana\n(:3000)"]
    PR --> AR["Alert Rules"]
    AR --> AM["Alertmanager\n(:9093)"]
    AM --> SL["Slack"]
```

Metrics flow: each filter exports OTLP to the collector every 10 seconds. The collector exposes a Prometheus scrape endpoint on port 8889. Prometheus scrapes it every 10 seconds. Grafana queries Prometheus. First metrics appear approximately 70 seconds after container startup.

## Files

```
examples/monitoring-demo/
  Makefile                    Make targets for all workflows
  docker-compose.pipelines.yaml  All 4 pipelines + monitoring stack
  docker-compose.yaml         Single-pipeline Docker workflow
  Dockerfile                  Builds openfilter-local:latest from source
  run_pipeline.py             Single Python pipeline (no Docker)
  run_pipeline_p4.py          P4 diamond-same-class Python reproducer
  filters/
    grayscale.py              Converts frames to grayscale
    resize.py                 Resizes frames
    stats.py                  Computes mean brightness
    slow_passthrough.py       Passes frames through with a configurable sleep (SLEEP_MS env var)
  timing_filter/filter.py     Passes frames through, logs filter_timings metadata every 30 frames
  verify_metrics.py           Verify health metrics in Prometheus
  verify_pipelines.py         Verify all 4 pipeline_ids report metrics
  verify_alerts.py            Verify Alertmanager config and send/resolve test alerts
  trigger_alert.py            Trigger real alert conditions (gpu, camera, disk)

docker/monitoring/
  docker-compose.monitoring.yaml   Monitoring stack container definitions
  otel-collector-config.yaml       OTLP receiver -> Prometheus exporter
  prometheus.yaml                  Scrape config and alerting
  alert-rules.yaml                 Alert rule definitions
  alertmanager.yaml                Routing template (Slack webhook via SLACK_WEBHOOK_URL)
  grafana-datasources.yaml         Auto-provisions Prometheus datasource (uid: openfilter_prometheus)
  grafana-dashboards.yaml          Auto-provisions dashboard from JSON file
  grafana-dashboard.json           OpenFilter Pipeline Monitor dashboard definition
```

## Troubleshooting

**No data in Grafana after 70 seconds?**
Run `make pipelines-status` to check all containers are up. Then check `make pipelines-verify` to confirm Prometheus is receiving metrics. If the monitoring stack was started separately from the pipelines, the OTEL collector may be on a different Docker network. Use `make pipelines-up` (single compose) rather than `make stack-up` + a separate compose to avoid this.

**GPU alert always firing?**
Expected on macOS. `nvidia-smi` is not available so `gpu_accessible` is always 0.

**DiskCriticalTest alert firing?**
Also expected. The test rule threshold is >10% disk usage, which fires on any non-empty disk. It exists only to verify the alerting pipeline works.

**Grafana shows "No data" on a panel?**
Check that the Pipeline variable is set (it defaults to All). If it was changed to a pipeline that no longer exists, reset it to All and re-select.
