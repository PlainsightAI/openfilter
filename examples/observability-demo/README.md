# OpenFilter Observability Demo

This demo showcases OpenFilter's comprehensive observability system with automatic metric collection, aggregation, and export to OpenLineage for Oleander integration.

## 🚀 **Features**

### **Automatic Metric Collection**
- **System Metrics**: CPU, memory, FPS, latency sent raw to OpenTelemetry collectors
- **Business Metrics**: Domain-specific metrics aggregated and sent only to OpenLineage
- **No PII Exposure**: Safe metric extraction without exposing sensitive data

### **Smart Histogram Generation**
- **Automatic Buckets**: Histogram boundaries auto-generated based on metric type
- **Custom Boundaries**: Option to specify custom bucket boundaries
- **Fixed Bucket Count**: Proper handling of bucket counts vs boundaries

### **Raw Data Export** (Optional)
- **Environment Variable**: `OPENLINEAGE_EXPORT_RAW_DATA=true` to enable
- **Frame Data**: Raw subject data included in OpenLineage heartbeats
- **Security**: Disabled by default to prevent PII exposure

### **Backward Compatibility**
- **Existing Filters**: Continue working without MetricSpec declarations
- **Gradual Migration**: Add metrics incrementally without breaking changes

## 📊 **Pipeline Overview**

```
Video Input → Custom Processor → Custom Visualizer → Output
     ↓              ↓                    ↓
  System Metrics  Business Metrics   System Metrics
     ↓              ↓                    ↓
OpenTelemetry   OpenLineage      OpenTelemetry
Collectors      (Oleander)       Collectors
```

## 🔧 **Setup**

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Create Sample Video**:
   ```bash
   python create_sample_video.py
   ```

3. **Configure Environment**:
   ```bash
   cp config.env.example config.env
   # Edit config.env with your settings
   ```

## 🏃‍♂️ **Running the Demo**

### **Basic Run** (Console Output Only)
```bash
source config.env
python app.py --input 'file://sample_video.mp4!loop' --fps 10
```

### **With OpenTelemetry** (Local Collector)
```bash
# Start local OTel collector
docker run -p 4317:4317 otel/opentelemetry-collector:latest

# Run demo
TELEMETRY_EXPORTER_TYPE=otlp \
TELEMETRY_EXPORTER_OTLP_ENDPOINT=http://localhost:4317 \
python app.py --input 'file://sample_video.mp4!loop' --fps 10
```

### **With OpenLineage** (Oleander Integration)
```bash
OPENLINEAGE_URL=https://your-oleander-instance.com \
OPENLINEAGE_API_KEY=your_api_key \
python app.py --input 'file://sample_video.mp4!loop' --fps 10
```

### **With Raw Data Export** (Advanced)
```bash
OPENLINEAGE_EXPORT_RAW_DATA=true \
python app.py --input 'file://sample_video.mp4!loop' --fps 10
```

## 📈 **Metrics Collected**

### **System Metrics** (Raw to OpenTelemetry)
- CPU usage, memory consumption
- FPS, latency, processing time
- GPU metrics (if available)

### **Business Metrics** (Aggregated to OpenLineage)
- `frames_processed`: Total frames processed
- `frames_with_detections`: Frames containing detections
- `detections_per_frame_histogram`: Distribution of detection counts
- `detection_confidence_histogram`: Confidence score distribution
- `processing_time_ms_histogram`: Processing time distribution
- `object_size_ratio_histogram`: Object size ratio distribution

## 🎛️ **Configuration Options**

### **Environment Variables**

| Variable | Description | Default |
|----------|-------------|---------|
| `TELEMETRY_EXPORTER_ENABLED` | Enable telemetry | `false` |
| `TELEMETRY_EXPORTER_TYPE` | Exporter type | `silent` |
| `OF_SAFE_METRICS` | Allowed metrics | `frames_processed,frames_with_detections,...` |
| `OPENLINEAGE_EXPORT_RAW_DATA` | Export raw frame data | `false` |
| `OPENLINEAGE_URL` | Oleander instance URL | None |
| `OPENLINEAGE_API_KEY` | Oleander API key | None |

### **Histogram Configuration**

#### **Automatic Buckets** (Recommended)
```python
MetricSpec(
    name="detections_per_frame",
    instrument="histogram",
    value_fn=lambda d: len(d.get("detections", [])),
    num_buckets=8  # Auto-generate 8 buckets
)
```

#### **Custom Boundaries**
```python
MetricSpec(
    name="object_size_ratio",
    instrument="histogram",
    value_fn=lambda d: d.get("size_ratio", 0.0),
    boundaries=[0.0, 0.1, 0.2, 0.3, 0.5, 0.7, 1.0]
)
```

## 🔍 **Debugging**

### **Enable Debug Logging**
```bash
LOG_LEVEL=debug python app.py --input 'file://sample_video.mp4!loop' --fps 10
```

### **Test Individual Components**
```bash
python test_demo.py
```

### **Check Metrics Flow**
Look for these log messages:
- `[Business Metrics] Registering metrics: ...`
- `[OpenLineage Export] Added counter: ...`
- `[OpenLineage Export] Added histogram: ...`

## 🏗️ **Architecture**

### **Metric Flow**
1. **Frame Processing**: Filters process frames and add data to `frame.data`
2. **Metric Extraction**: `TelemetryRegistry` extracts values using `MetricSpec.value_fn`
3. **Aggregation**: OpenTelemetry SDK aggregates metrics over time
4. **Export**: `OTelLineageExporter` converts aggregated metrics to OpenLineage facets
5. **Heartbeat**: Metrics sent to Oleander via OpenLineage heartbeat

### **Security Model**
- **Allowlist**: Only explicitly allowed metrics are exported
- **No PII**: Raw subject data never included in metrics (unless explicitly enabled)
- **Separation**: System metrics go to collectors, business metrics go to OpenLineage

## 🚨 **Troubleshooting**

### **Common Issues**

1. **No Metrics in Oleander**:
   - Check `OPENLINEAGE_URL` and `OPENLINEAGE_API_KEY`
   - Verify `OF_SAFE_METRICS` includes desired metrics

2. **Histogram Bucket Mismatch**:
   - Fixed automatically in the bridge
   - Check logs for warnings about bucket count mismatches

3. **Raw Data Not Exporting**:
   - Ensure `OPENLINEAGE_EXPORT_RAW_DATA=true`
   - Check logs for raw data export messages

### **Log Messages**
- ✅ Green: Business metrics registration
- 🔴 Red: Error messages
- 🟡 Yellow: Warning messages
- 📊 Blue: Metric export information

## 📚 **Advanced Usage**

### **Adding Custom Metrics**
```python
class MyFilter(Filter):
    metric_specs = [
        MetricSpec(
            name="my_custom_metric",
            instrument="histogram",
            value_fn=lambda d: d.get("my_value", 0),
            num_buckets=10
        )
    ]
```

### **Custom Histogram Boundaries**
```python
MetricSpec(
    name="custom_histogram",
    instrument="histogram",
    value_fn=lambda d: d.get("value", 0),
    boundaries=[0, 10, 50, 100, 500, 1000]
)
```

### **Raw Data Export**
```bash
# Enable raw data export
export OPENLINEAGE_EXPORT_RAW_DATA=true

# Run pipeline
python app.py --input 'file://sample_video.mp4!loop' --fps 10
```

## 🤝 **Contributing**

This demo serves as a reference implementation for OpenFilter observability. To contribute:

1. Add new metric types to `MetricSpec`
2. Implement custom histogram bucket strategies
3. Add new export formats
4. Improve security and PII protection

## 📄 **License**

This demo is part of the OpenFilter project and follows the same license terms. 