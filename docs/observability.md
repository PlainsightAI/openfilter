# OpenFilter Observability System

This document describes the new observability system in OpenFilter that provides safe, aggregated metrics without PII leakage.

## Overview

The observability system is built around three key principles:

1. **No PII in metrics** - Only numeric, aggregated data leaves the process
2. **Declarative metrics** - Filters declare what they want to measure, not how
3. **Open standards** - Uses OpenTelemetry for aggregation and OpenLineage for export

## Architecture

```
Filter Implementation
├── Declares MetricSpec(s)
├── Records measurements
└── No aggregation code

OpenTelemetry SDK
├── Counter, Histogram instruments
├── Native explicit-bucket histogram aggregation
└── Export every N seconds via MetricReader

OTel→OL Bridge (OTelLineageExporter)
├── Converts Counter/Histogram to JSON fragments
├── Builds one `run.facet` dict
└── Calls `OpenFilterLineage.update_heartbeat()`

OpenFilterLineage emitter
├── Emits RUNNING heartbeat every N seconds
└── START / COMPLETE unchanged
```

## Declaring Metrics

Filters declare metrics using the `metric_specs` class attribute:

```python
from openfilter.filter_runtime.filter import Filter
from openfilter.telemetry.specs import MetricSpec

class MyFilter(Filter):
    metric_specs = [
        # Count frames processed
        MetricSpec(
            name="frames_processed",
            instrument="counter",
            value_fn=lambda d: 1
        ),
        
        # Count frames with detections
        MetricSpec(
            name="frames_with_detection",
            instrument="counter",
            value_fn=lambda d: 1 if d.get("detections") else 0
        ),
        
        # Distribution of detections per frame
        MetricSpec(
            name="detections_per_frame",
            instrument="histogram",
            value_fn=lambda d: len(d.get("detections", [])),
            boundaries=[0, 1, 2, 5, 10]
        )
    ]
```

### MetricSpec Parameters

- `name`: The metric name (e.g., "frames_with_plate")
- `instrument`: Either "counter" or "histogram"
- `value_fn`: Function that extracts a numeric value from frame data
- `boundaries`: For histograms, the bucket boundaries (optional)

## Configuration

### Environment Variables

- `TELEMETRY_EXPORTER_ENABLED`: Enable/disable telemetry (default: false)
- `OF_SAFE_METRICS`: Comma-separated list of allowed metric names
- `OF_SAFE_METRICS_FILE`: Path to YAML file with safe_metrics list

### YAML Configuration

```yaml
safe_metrics:
  - frames_*
  - plates_per_frame_histogram
  - ocr_confidence
```

## Example Output

Oleander will receive heartbeat events with facets like:

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

## Migration Guide

### For Filter Authors

1. Add `metric_specs` class attribute to your filter
2. Declare safe metrics using `MetricSpec`
3. Remove any PII-forwarding logic from `process_frames_metadata`

### For Deployment

1. Set `TELEMETRY_EXPORTER_ENABLED=true`
2. Configure `OF_SAFE_METRICS` or `OF_SAFE_METRICS_FILE`
3. Verify metrics appear in Oleander without PII

## Security

- **Allowlist enforcement**: Only metrics in the allowlist are exported
- **No PII**: Only numeric, aggregated values leave the process
- **Runtime validation**: The bridge validates all metric names before export

## Benefits

- **Standards compliance**: Uses OpenTelemetry for aggregation
- **Reusable**: Same declaration mechanism works for all filters
- **Safe**: Zero PII risk through allowlist and numeric-only export
- **Flexible**: Easy to add new metrics without code changes 