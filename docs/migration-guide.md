# OpenFilter Observability Migration Guide

This guide helps you migrate from the old telemetry structure to the new unified observability system.

## Old Structure (Confusing)

```
openfilter/
├── telemetry/                    # New observability system
├── filter_runtime/open_telemetry/ # Old OpenTelemetry client
└── lineage/                      # Old OpenLineage client
```

## New Structure (Clean)

```
openfilter/
├── observability/                # All observability functionality
│   ├── __init__.py
│   ├── specs.py                 # MetricSpec dataclass
│   ├── registry.py              # TelemetryRegistry
│   ├── bridge.py                # OTelLineageExporter
│   ├── config.py                # Allowlist configuration
│   ├── client.py                # OpenTelemetry client
│   └── lineage.py               # OpenLineage client
├── filter_runtime/              # Core filter runtime (no telemetry)
└── cli/                         # Command line interface
```

## Migration Steps

### 1. Update Imports

**Old:**
```python
from openfilter.telemetry.specs import MetricSpec
from openfilter.telemetry.registry import TelemetryRegistry
from openfilter.lineage import openlineage_client as FilterLineage
from openfilter.filter_runtime.open_telemetry.open_telemetry_client import OpenTelemetryClient
```

**New:**
```python
from openfilter.observability import MetricSpec, TelemetryRegistry, OpenFilterLineage, OpenTelemetryClient
```

### 2. Update Filter Declarations

**Old:**
```python
class MyFilter(Filter):
    # No metric declarations
    pass
```

**New:**
```python
class MyFilter(Filter):
    metric_specs = [
        MetricSpec(
            name="frames_processed",
            instrument="counter",
            value_fn=lambda d: 1
        )
    ]
```

### 3. Environment Variables

The environment variables remain the same:

- `TELEMETRY_EXPORTER_ENABLED`: Enable/disable telemetry
- `OF_SAFE_METRICS`: Comma-separated list of allowed metrics
- `OF_SAFE_METRICS_FILE`: Path to YAML file with safe metrics

### 4. Configuration Files

YAML configuration files remain the same:

```yaml
safe_metrics:
  - frames_*
  - plates_per_frame_histogram
  - ocr_confidence
```

## Benefits of the New Structure

1. **Single Package**: All observability code is in one place
2. **Clear Dependencies**: Easy to understand what depends on what
3. **Better Organization**: Related functionality is grouped together
4. **Simplified Imports**: One import statement for all observability features

## Backward Compatibility

The old packages will continue to work during a transition period, but they are deprecated:

- `openfilter.telemetry.*` → `openfilter.observability.*`
- `openfilter.lineage.*` → `openfilter.observability.*`
- `openfilter.filter_runtime.open_telemetry.*` → `openfilter.observability.*`

## Testing

To test the new structure:

```bash
# Run the observability tests
python -m pytest tests/test_telemetry.py -v

# Run a simple filter with metrics
export TELEMETRY_EXPORTER_ENABLED=true
export OF_SAFE_METRICS="frames_processed,frames_with_plate"
python examples/hello-world/filter_license_plate_pipeline_demo/license_plate_filter_example.py
```

## Next Steps

1. Update your filter implementations to use `metric_specs`
2. Test with the new observability package
3. Remove old telemetry imports
4. Verify metrics appear in Oleander without PII 