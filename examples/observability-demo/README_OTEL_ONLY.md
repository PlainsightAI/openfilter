# OTEL-Only Observability Demo

This demo shows how to use OpenFilter with **OpenTelemetry (OTEL) collectors only**, without OpenLineage. It demonstrates connecting to cloud OTEL endpoints and exporting both raw and aggregated metrics.

## 🎯 What This Demo Shows

- **OTEL-Only Export**: Send metrics directly to OTEL collectors
- **Cloud Integration**: Connect to cloud OTEL endpoints (GCP, AWS, Azure)
- **Raw vs Aggregated**: Control how metrics are processed before export
- **Custom MetricSpecs**: Define business metrics with `target="otel"`
- **System Metrics**: Automatic collection of FPS, CPU, memory metrics
- **Safe Metrics**: Use allowlists to prevent PII leakage

## 🏗️ Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   OpenFilter    │    │  OpenTelemetry   │    │  Cloud OTEL     │
│                 │    │     SDK          │    │   Collector     │
│ ┌─────────────┐ │    │                  │    │                 │
│ │System Metrics│ ├────┤ Raw Export       ├────┤ Your Cloud      │
│ │(fps, cpu...)│ │    │                  │    │ Provider        │
│ └─────────────┘ │    │                  │    │ (GCP/AWS/Azure) │
│                 │    │                  │    │                 │
│ ┌─────────────┐ │    │                  │    │                 │
│ │MetricSpecs  │ ├────┤ Aggregated       ├────┤                 │
│ │(business)   │ │    │ Export           │    │                 │
│ └─────────────┘ │    │                  │    │                 │
└─────────────────┘    └──────────────────┘    └─────────────────┘
```

## 🚀 Quick Start

### 1. Configure Your Cloud OTEL Endpoint

Edit `config_otel_only.env`:

```bash
# Replace with your actual OTEL collector URL
OTEL_EXPORTER_OTLP_ENDPOINT=https://your-otel-collector.com:4317

# Add authentication if required
OTEL_EXPORTER_OTLP_HEADERS=authorization=Bearer YOUR_TOKEN
```

### 2. Run the Demo

```bash
# Install dependencies
pip install -r requirements.txt

# Run the OTEL-only demo
python app_otel_only.py
```

### 3. Monitor Your Cloud Dashboard

Check your cloud provider's monitoring dashboard to see the exported metrics.

## ☁️ Cloud Provider Setup

### Google Cloud Platform (GCP)

```bash
# Set up GCP OTEL collector
OTEL_EXPORTER_OTLP_ENDPOINT=https://your-project.googleapis.com:4317
OTEL_EXPORTER_OTLP_HEADERS=authorization=Bearer $(gcloud auth print-access-token)
```

### Amazon Web Services (AWS)

```bash
# Set up AWS X-Ray OTEL collector  
OTEL_EXPORTER_OTLP_ENDPOINT=https://your-region.awsxray.amazonaws.com:4317
OTEL_EXPORTER_OTLP_HEADERS=x-aws-access-key-id=YOUR_KEY,x-aws-secret-access-key=YOUR_SECRET
```

### Microsoft Azure

```bash
# Set up Azure Monitor OTEL collector
OTEL_EXPORTER_OTLP_ENDPOINT=https://your-workspace.azure.com:4317
OTEL_EXPORTER_OTLP_HEADERS=x-api-key=YOUR_API_KEY
```

### Custom OTEL Collector

```bash
# Set up custom OTEL collector (e.g., Jaeger, Zipkin)
OTEL_EXPORTER_OTLP_ENDPOINT=https://your-custom-otel.com:4317
OTEL_EXPORTER_OTLP_HEADERS=authorization=Bearer YOUR_TOKEN
```

## 📊 Metrics Configuration

### Export Modes

Control how metrics are processed:

```python
# In your MetricSpec or configuration
export_mode="raw"        # Send raw values directly
export_mode="aggregated" # Let OTel SDK aggregate first  
export_mode="both"       # Send both raw and aggregated
```

### Targets

Control where metrics go:

```python
# In your MetricSpec
target="otel"        # Only to OTEL collectors
target="openlineage" # Only to OpenLineage (not used in this demo)
target="both"        # To both destinations
```

### Example MetricSpec for OTEL-Only

```python
from openfilter.observability import MetricSpec

metric_specs = [
    MetricSpec(
        name="detections_per_frame",
        instrument="histogram", 
        value_fn=lambda d: len(d.get("detections", [])),
        export_mode="both",      # Send raw and aggregated
        target="otel",           # Only to OTEL collectors
        num_buckets=10           # Auto-generate histogram buckets
    ),
    MetricSpec(
        name="frames_processed",
        instrument="counter",
        value_fn=lambda d: 1,
        export_mode="raw",       # Send raw values only
        target="otel"            # Only to OTEL collectors  
    )
]
```

## 🔒 Safe Metrics

Use `safe_metrics_otel.yaml` to control which metrics are exported:

```yaml
# Include OTEL configuration
opentelemetry:
  endpoint: "https://your-otel-collector.com:4317"
  headers: "authorization=Bearer YOUR_TOKEN"
  enabled: true

# Define safe metrics (no PII)
safe_metrics:
  - "detections_per_frame"
  - "confidence_score"
  - "processing_time"
  - "fps"
  - "cpu" 
  - "memory"
  - "*_histogram"  # Wildcard patterns
```

## 🛠️ Configuration Options

### Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `OTEL_EXPORTER_OTLP_ENDPOINT` | Your OTEL collector URL | `https://otel.example.com:4317` |
| `OTEL_EXPORTER_OTLP_HEADERS` | Authentication headers | `authorization=Bearer TOKEN` |
| `OTEL_EXPORTER_OTLP_PROTOCOL` | Protocol (grpc/http) | `grpc` |
| `TELEMETRY_EXPORTER_ENABLED` | Enable telemetry | `true` |
| `OTEL_EXPORT_INTERVAL` | Export interval (seconds) | `30` |
| `OF_SAFE_METRICS_FILE` | Path to allowlist YAML | `safe_metrics_otel.yaml` |

### YAML Configuration

You can also configure OTEL in the YAML file:

```yaml
opentelemetry:
  endpoint: "https://your-collector.com:4317"
  headers: "auth=token"
  protocol: "grpc"
  export_interval: 30
  enabled: true
```

## 🔍 Monitoring & Debugging

### Check OTEL Export

```bash
# Enable debug logging
export OTEL_LOG_LEVEL=DEBUG

# Run the demo
python app_otel_only.py
```

### Verify Metrics

Look for these log messages:

```
✅ Using OTEL config: endpoint=https://your-collector.com:4317
✅ [OTEL Metrics] Created counter: frames_processed
✅ [OTEL Metrics] Created histogram: detections_per_frame
```

### Common Issues

1. **No metrics in cloud dashboard**
   - Check `OTEL_EXPORTER_OTLP_ENDPOINT` is correct
   - Verify authentication headers
   - Confirm `TELEMETRY_EXPORTER_ENABLED=true`

2. **Authentication errors**
   - Check `OTEL_EXPORTER_OTLP_HEADERS` format
   - Verify your cloud credentials/tokens

3. **Connection timeouts**
   - Check network connectivity
   - Verify OTEL collector is running
   - Try different protocol (grpc vs http)

## 📁 Files Overview

- `app_otel_only.py` - Main OTEL-only demo application
- `config_otel_only.env` - Environment configuration for OTEL
- `safe_metrics_otel.yaml` - Safe metrics allowlist with OTEL config
- `custom_processor.py` - Updated with OTEL-specific MetricSpecs
- `README_OTEL_ONLY.md` - This documentation

## 🆚 OTEL vs OpenLineage

| Feature | OTEL-Only | OpenLineage | 
|---------|-----------|-------------|
| **Purpose** | Metrics & traces | Data lineage & metadata |
| **Export Format** | OTLP | JSON events |
| **Aggregation** | In OTel SDK | In bridge layer |
| **Destinations** | Cloud collectors | Lineage systems |
| **Raw Data** | Supported | Configurable |

## 🎯 Next Steps

1. **Set up your cloud OTEL collector**
2. **Configure authentication** 
3. **Define your custom MetricSpecs** with `target="otel"`
4. **Run the demo** and check your cloud dashboard
5. **Scale to production** with proper monitoring setup

For questions or issues, check the main OpenFilter documentation or open an issue.
