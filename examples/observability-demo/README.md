# OpenFilter Observability Demo

This example demonstrates the complete observability system in OpenFilter, showing how to use both standard filters and custom filters with and without MetricSpec declarations.

## 🏗️ Pipeline Architecture

```
VideoIn → CustomProcessor (with MetricSpecs) → CustomVisualizer (without MetricSpecs) → VideoOut
```

## 📊 Observability Features Demonstrated

### **System Metrics (All Filters)**
- CPU usage, memory usage, FPS, latency
- Sent to OpenTelemetry for real-time monitoring
- Aggregated by OTel SDK and sent to OpenLineage

### **Business Metrics (CustomProcessor Only)**
- `frames_processed`: Total frames processed
- `frames_with_detections`: Frames containing detections
- `detections_per_frame`: Histogram of detections per frame
- `detection_confidence`: Histogram of detection confidence scores
- Sent **only** to OpenLineage via OTelLineageExporter bridge

## 🔧 Custom Filters

### **CustomProcessor (with MetricSpecs)**
- Processes video frames and adds detection data
- Declares business metrics using MetricSpec
- Demonstrates safe metric extraction from frame.data

### **CustomVisualizer (without MetricSpecs)**
- Creates visual overlays on processed frames
- No MetricSpec declarations (backward compatibility)
- Still emits system metrics to OpenTelemetry

## 🚀 Running the Demo

### **1. Basic Run (Console Output)**
```bash
cd examples/observability-demo
python app.py
```

### **2. With OpenTelemetry (GCM/Prometheus)**
```bash
export TELEMETRY_EXPORTER_ENABLED=true
export TELEMETRY_EXPORTER_TYPE=otlp
export TELEMETRY_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
python app.py
```

### **3. With OpenLineage (Oleander)**
```bash
export TELEMETRY_EXPORTER_ENABLED=true
export OPENLINEAGE_URL=https://oleander.dev
export OPENLINEAGE_API_KEY=your_api_key
export OF_SAFE_METRICS=frames_processed,frames_with_detections,detections_per_frame_histogram,detection_confidence_histogram
python app.py
```

### **4. Full Observability Stack**
```bash
export TELEMETRY_EXPORTER_ENABLED=true
export TELEMETRY_EXPORTER_TYPE=otlp
export TELEMETRY_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
export OPENLINEAGE_URL=https://oleander.dev
export OPENLINEAGE_API_KEY=your_api_key
export OF_SAFE_METRICS=frames_processed,frames_with_detections,detections_per_frame_histogram,detection_confidence_histogram
python app.py
```

## 📈 Expected Metrics

### **System Metrics (All Filters)**
- `CustomProcessor_cpu`: CPU usage percentage
- `CustomProcessor_mem`: Memory usage in MB
- `CustomProcessor_fps`: Frames per second
- `CustomVisualizer_cpu`: CPU usage percentage
- `CustomVisualizer_mem`: Memory usage in MB
- `CustomVisualizer_fps`: Frames per second

### **Business Metrics (CustomProcessor Only)**
- `frames_processed`: Total frames processed
- `frames_with_detections`: Frames with detections
- `detections_per_frame_histogram`: Distribution of detections per frame
- `detection_confidence_histogram`: Distribution of confidence scores

## 🔍 Monitoring

### **OpenTelemetry (System Metrics)**
- Real-time system monitoring
- CPU, memory, FPS, latency
- Available in GCM, Prometheus, etc.

### **OpenLineage (Business Metrics)**
- Business intelligence and analytics
- Aggregated metrics for dashboards
- Available in Oleander UI

## 🛡️ Security Features

- **Allowlist Protection**: Only declared metrics are exported
- **PII-Free**: No raw data ever leaves the system
- **Declarative**: Metrics are declared, not hardcoded
- **Backward Compatible**: Filters without MetricSpecs still work

## 📁 File Structure

```
observability-demo/
├── README.md                 # This file
├── app.py                    # Main application
├── custom_processor.py       # Custom filter with MetricSpecs
├── custom_visualizer.py      # Custom filter without MetricSpecs
├── sample_video.mp4          # Sample video for processing
└── output/                   # Output directory
    ├── processed_video.mp4   # Final processed video
    └── analytics.json        # Analytics data
``` 