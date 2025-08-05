# OpenFilter Metrics Architecture

OpenFilter has **two distinct metric systems** that serve different purposes and export to different destinations.

## 1. Filter Metrics (System Metrics)

**Purpose**: Monitor filter performance and system health
**Source**: `openfilter/filter_runtime/metrics.py`
**Destination**: OpenTelemetry → GCM/Prometheus
**Data**: CPU, memory, FPS, latency, GPU usage, etc.
**Aggregation**: **NO** - raw metrics sent directly

### Configuration
```bash
export TELEMETRY_EXPORTER_ENABLED=true
export TELEMETRY_EXPORTER_TYPE=otlp  # or console, prometheus, etc.
```

### Example Output (Raw Metrics)
```json
{
  "fps": 30.5,
  "cpu": 45.2,
  "mem": 2.1,
  "lat_in": 15.3,
  "lat_out": 12.7,
  "gpu0": 78.5,
  "gpu0_mem": 4.2
}
```

## 2. Subject Data Metrics (Business Metrics)

**Purpose**: Monitor business logic and data processing
**Source**: Frame data via `MetricSpec` declarations
**Destination**: OpenLineage → Oleander/UI
**Data**: Detections, counts, distributions, etc.
**Aggregation**: **YES** - safe, PII-free summaries

### Configuration
```bash
export TELEMETRY_EXPORTER_ENABLED=true
export OF_SAFE_METRICS="frames_processed,frames_with_plate"
```

### Example Output (Aggregated Metrics)
```json
{
  "frames_processed": 150,
  "frames_with_plate": 27,
  "plates_per_frame_histogram": {
    "buckets": [0, 1, 2, 5],
    "counts": [118, 22, 8, 2],
    "count": 150,
    "sum": 36
  }
}
```

## Architecture Diagram

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Filter        │    │   OpenTelemetry  │    │   GCM/Prometheus│
│   Metrics       │───▶│   Client         │───▶│   (Raw System   │
│   (metrics.py)  │    │   (Raw Metrics)  │    │    Metrics)     │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                                │
                                ▼
                       ┌──────────────────┐
                       │   OpenLineage    │
                       │   Bridge         │
                       │   (Aggregated)   │
                       └──────────────────┘
                                │
                                ▼
                       ┌──────────────────┐    ┌─────────────────┐
                       │   OpenLineage    │───▶│   Oleander/UI   │
                       │   Client         │    │   (Aggregated   │
                       └──────────────────┘    │    Business     │
                                              │    Metrics)     │
                                              └─────────────────┘

┌─────────────────┐    ┌──────────────────┐
│   Frame Data    │    │   MetricSpec     │
│   (frame.data)  │───▶│   Registry       │
└─────────────────┘    └──────────────────┘
```

## Key Differences

### OpenTelemetry (System Metrics)
- ✅ **Raw metrics** - no aggregation
- ✅ **Real-time monitoring** - immediate values
- ✅ **System health** - CPU, memory, performance
- ✅ **Direct export** - metrics sent as-is

### OpenLineage (Business Metrics)
- ✅ **Aggregated metrics** - safe summaries
- ✅ **Business intelligence** - trends and patterns
- ✅ **PII-free** - only numeric, safe data
- ✅ **UI-friendly** - formatted for dashboards

## Usage Scenarios

### Scenario 1: System Monitoring Only
```bash
export TELEMETRY_EXPORTER_ENABLED=true
export TELEMETRY_EXPORTER_TYPE=otlp
# No MetricSpecs needed
# → Raw system metrics sent to GCM/Prometheus
```

### Scenario 2: Business Monitoring Only
```bash
export TELEMETRY_EXPORTER_ENABLED=true
export OF_SAFE_METRICS="frames_processed,frames_with_plate"
# Filters with MetricSpecs
# → Aggregated business metrics sent to Oleander
```

### Scenario 3: Both Systems
```bash
export TELEMETRY_EXPORTER_ENABLED=true
export TELEMETRY_EXPORTER_TYPE=otlp
export OF_SAFE_METRICS="frames_processed,frames_with_plate"
# Filters with MetricSpecs
# → Raw system metrics to GCM/Prometheus + Aggregated business metrics to Oleander
```

## Implementation Details

### Filter Metrics (System) - Raw Export
- **Direct recording** - no aggregation
- **Real-time values** - immediate export
- **System monitoring** - performance tracking
- **OpenTelemetry native** - standard metrics

### Subject Data Metrics (Business) - Aggregated Export
- **Safe aggregation** - PII-free summaries
- **Batch processing** - periodic export
- **Business intelligence** - trend analysis
- **OpenLineage format** - UI-friendly data

## Backward Compatibility

✅ **Filter metrics work unchanged** - existing OpenTelemetry functionality preserved
✅ **No breaking changes** - old filters work without modification
✅ **Opt-in business metrics** - only enabled when filters declare `metric_specs`
✅ **Independent systems** - can enable one, both, or neither

## Migration Path

1. **Immediate**: System metrics work as before (raw export)
2. **Gradual**: Add `metric_specs` to filters when you want business metrics (aggregated export)
3. **Optional**: Enable OpenLineage export when you want UI monitoring 