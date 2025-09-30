# MQTT Bridge Filter

The MQTT Bridge filter is an output filter for OpenFilter that publishes incoming frame data and images to MQTT brokers. It supports flexible topic mapping, QoS settings, message retention, and automatic serialization of various data types including images as base64-encoded data.

## Overview

The MQTT Bridge filter is designed to handle MQTT publishing scenarios where you need to:
- Publish frame data and images to MQTT brokers
- Map OpenFilter topics to MQTT topics with flexible routing
- Control message quality of service (QoS) and retention
- Serialize complex data structures including images
- Handle authentication and connection management
- Support sampling intervals for rate-limited publishing
- Integrate with IoT platforms and monitoring systems

## Key Features

- **Flexible Topic Mapping**: Map OpenFilter topics to MQTT topics with path-based routing
- **Image Publishing**: Automatically encode images as base64 JPEG data
- **Data Serialization**: Handle complex nested data structures and arrays
- **QoS Control**: Configurable Quality of Service levels (0, 1, 2)
- **Message Retention**: Control message retention on broker
- **Authentication**: Support for username/password authentication
- **Connection Management**: Automatic reconnection with exponential backoff
- **Sampling Intervals**: Rate-limited publishing for high-frequency data
- **Multiple Data Types**: Support for JSON, binary, and custom data formats

## Configuration

### Basic Configuration

```python
from openfilter.filter_runtime.filter import Filter
from openfilter.filter_runtime.filters.mqtt_out import MQTTOut

# Simple MQTT publishing
Filter.run_multi([
    # ... other filters above
    (MQTTOut, dict(
        sources='tcp://localhost:5550',
        outputs='mqtt://localhost:1883/my_base_topic',
    )),
])
```

### Advanced Configuration with Topic Mapping

```python
# Complex topic mapping with QoS and retention
Filter.run_multi([
    # ... other filters above
    (MQTTOut, dict(
        sources='tcp://localhost:5550',
        broker_host='mqtt.example.com',
        broker_port=8883,
        username='myuser',
        password='mypass',
        base_topic='sensors/camera',
        mappings=[
            'main/image > frames!qos=0',
            'main/data > metadata!qos=2!retain=true',
            'detection/data/detections > detections!qos=1',
        ],
        interval=2.0,  # Sample every 2 seconds
    )),
])
```

### Environment Variables

You can configure via environment variables:

```bash
export FILTER_SOURCES="tcp://localhost:5550"
export FILTER_BROKER_HOST="localhost"
export FILTER_BROKER_PORT="1883"
export FILTER_BASE_TOPIC="my_app/sensors"
export FILTER_INTERVAL="1.0"
export DEBUG_MQTT="true"
```

## MQTT Connection Configuration

### Broker Settings
- `broker_host`: MQTT broker hostname (default: 'localhost')
- `broker_port`: MQTT broker port (default: 1883)
- `username`: Authentication username (optional)
- `password`: Authentication password (optional)
- `client_id`: MQTT client ID (auto-generated if not specified)
- `keepalive`: Keep-alive interval in seconds (default: 60)

### Connection Management
- **Automatic Reconnection**: Exponential backoff on connection failures
- **Connection Timeout**: Configurable timeout settings
- **Error Handling**: Graceful handling of connection issues
- **Client ID Management**: Automatic or custom client ID generation

## Topic Mapping

The MQTTOut filter provides flexible topic mapping between OpenFilter topics and MQTT topics:

### Basic Mapping Syntax
```
"src_topic/src_path > dst_topic !qos=1 !retain=true"
```

### Mapping Components

#### Source Specification
- `topic`: OpenFilter topic name (e.g., 'main', 'camera1', 'detection')
- `topic/image`: Frame image data
- `topic/data`: Frame metadata dictionary
- `topic/data/subfield`: Specific field in metadata
- `topic/data/nested/field`: Deep nested field access

#### Destination Specification
- `> topic_name`: MQTT topic name (relative to base_topic)
- No destination: Uses default topic names based on source path

#### Options
- `!qos=0|1|2`: Quality of Service level
- `!retain=true|false`: Message retention flag

### Mapping Examples

#### Simple Topic Mapping
```python
mappings = [
    'main',                    # main/image → base_topic/frames, main/data → base_topic/data
    'camera1/image > camera1', # camera1/image → base_topic/camera1
    'detection/data > det',    # detection/data → base_topic/det
]
```

#### Path-Based Mapping
```python
mappings = [
    'main/image > frames',                    # Image data to frames topic
    'main/data > metadata',                   # All metadata to metadata topic
    'main/data/detections > detections',      # Only detections field
    'main/data/timestamp > timestamp',        # Only timestamp field
]
```

#### Advanced Mapping with Options
```python
mappings = [
    'main/image > frames!qos=0',                    # Images with QoS 0
    'main/data > metadata!qos=2!retain=true',      # Metadata with QoS 2 and retention
    'detection/data/detections > detections!qos=1', # Detections with QoS 1
]
```

#### Nested Data Access
```python
mappings = [
    'camera1/data/sensors/temperature > temp',
    'camera1/data/sensors/humidity > humidity',
    'camera1/data/status/battery > battery',
    'camera1/data/config/interval > config_interval',
]
```

## Data Serialization

The MQTTOut filter automatically handles serialization of various data types:

### Supported Data Types
- **JSON Objects**: Dictionaries and nested structures
- **Arrays**: Lists and tuples
- **Images**: Base64-encoded JPEG data
- **Binary Data**: Base64-encoded bytes
- **Primitives**: Strings, integers, floats
- **Datetime**: ISO format timestamps
- **NumPy Arrays**: Converted to appropriate format

### Image Handling
- **Automatic Encoding**: Images are encoded as JPEG and then base64
- **Format Detection**: Supports various input formats (BGR, RGB, grayscale)
- **Compression**: Uses JPEG compression for efficient transmission
- **Metadata**: Image dimensions and format information included

### Data Structure Examples

#### Input Frame Data
```python
frame.data = {
    'detections': [
        {'class': 'person', 'confidence': 0.95, 'bbox': [100, 200, 300, 400]},
        {'class': 'car', 'confidence': 0.87, 'bbox': [500, 100, 700, 300]}
    ],
    'timestamp': 1640995200.123,
    'camera_id': 'cam001',
    'temperature': 23.5
}
```

#### MQTT Output
```json
{
  "detections": [
    {"class": "person", "confidence": 0.95, "bbox": [100, 200, 300, 400]},
    {"class": "car", "confidence": 0.87, "bbox": [500, 100, 700, 300]}
  ],
  "timestamp": "2022-01-01T00:00:00.123000",
  "camera_id": "cam001",
  "temperature": 23.5
}
```

## QoS and Message Retention

### Quality of Service (QoS) Levels
- **QoS 0**: At most once delivery (fire and forget)
- **QoS 1**: At least once delivery (acknowledged)
- **QoS 2**: Exactly once delivery (assured)

### Default QoS Settings
- **Images**: QoS 0 (fastest, suitable for real-time video)
- **Data**: QoS 2 (most reliable, suitable for critical metadata)
- **Customizable**: Override per mapping

### Message Retention
- **Retain Flag**: Messages persist on broker for new subscribers
- **Use Cases**: Configuration data, status information
- **Performance**: Retained messages consume broker memory

## Sampling and Rate Limiting

### Sampling Intervals
```python
interval=2.0  # Sample and publish every 2 seconds
```

### Behavior
- **Accumulation**: Frames are accumulated during interval
- **Latest Data**: Only the latest frame per topic is published
- **Rate Limiting**: Prevents overwhelming MQTT broker
- **Efficiency**: Reduces network traffic and processing load

### Use Cases
- **High-Frequency Data**: Video streams, sensor readings
- **Resource Constraints**: Limited bandwidth or broker capacity
- **Monitoring**: Periodic status updates
- **Logging**: Regular data snapshots

## Usage Examples

### Example 1: Basic Image Publishing
```python
Filter.run_multi([
    # ... other filters above
    (VideoIn, dict(
        sources='file://input.mp4',
        outputs='tcp://*:5550',
    )),
    (MQTTOut, dict(
        sources='tcp://localhost:5550',
        outputs='mqtt://localhost:1883/camera/stream',
        mappings=['main/image > frames!qos=0'],
    )),
])
```

**Behavior:** Publishes video frames as base64-encoded JPEG data to MQTT.

### Example 2: Sensor Data Publishing
```python
Filter.run_multi([
    # ... other filters above
    (REST, dict(
        sources='http://localhost:8000',
        outputs='tcp://*:5550',
    )),
    (MQTTOut, dict(
        sources='tcp://localhost:5550',
        broker_host='iot.example.com',
        base_topic='sensors/weather',
        mappings=[
            'main/data/temperature > temperature!qos=2!retain=true',
            'main/data/humidity > humidity!qos=2!retain=true',
            'main/data/pressure > pressure!qos=2!retain=true',
        ],
    )),
])
```

**Behavior:** Publishes weather sensor data with QoS 2 and retention.

### Example 3: Object Detection Results
```python
Filter.run_multi([
    # ... other filters above
    (ObjectDetectionFilter, dict(
        sources='tcp://localhost:5550',
        outputs='tcp://*:5552',
    )),
    (MQTTOut, dict(
        sources='tcp://localhost:5552',
        base_topic='ai/detections',
        mappings=[
            'main/image > frames!qos=0',
            'main/data/detections > detections!qos=1',
            'main/data/confidence > confidence!qos=1',
        ],
        interval=1.0,  # 1 FPS for detections
    )),
])
```

**Behavior:** Publishes detection results with images and metadata.

### Example 4: Multi-Camera Setup
```python
Filter.run_multi([
    # ... other filters above
    (VideoIn, dict(
        sources='file://camera1.mp4;cam1, file://camera2.mp4;cam2',
        outputs='tcp://*:5550',
    )),
    (MQTTOut, dict(
        sources='tcp://localhost:5550',
        base_topic='surveillance',
        mappings=[
            'cam1/image > camera1/frames!qos=0',
            'cam1/data > camera1/meta!qos=1',
            'cam2/image > camera2/frames!qos=0',
            'cam2/data > camera2/meta!qos=1',
        ],
    )),
])
```

**Behavior:** Publishes multiple camera streams to separate MQTT topics.

### Example 5: Configuration and Status
```python
Filter.run_multi([
    # ... other filters above
    (SystemMonitor, dict(
        sources='internal://system',
        outputs='tcp://*:5550',
    )),
    (MQTTOut, dict(
        sources='tcp://localhost:5550',
        base_topic='system/status',
        mappings=[
            'main/data/cpu > cpu_usage!qos=2!retain=true',
            'main/data/memory > memory_usage!qos=2!retain=true',
            'main/data/disk > disk_usage!qos=2!retain=true',
            'main/data/temperature > temperature!qos=2!retain=true',
        ],
        interval=30.0,  # Status every 30 seconds
    )),
])
```

**Behavior:** Publishes system status with retention for monitoring.

### Example 6: Alert System
```python
Filter.run_multi([
    # ... other filters above
    (AnomalyDetection, dict(
        sources='tcp://localhost:5550',
        outputs='tcp://*:5552',
    )),
    (MQTTOut, dict(
        sources='tcp://localhost:5552',
        base_topic='alerts',
        mappings=[
            'main/data/alert > alerts!qos=2!retain=true',
            'main/image > alert_images!qos=1',
            'main/data/timestamp > alert_timestamp!qos=2',
        ],
    )),
])
```

**Behavior:** Publishes alerts with high reliability and retention.

## Error Handling and Reliability

### Connection Management
- **Automatic Reconnection**: Exponential backoff on failures
- **Connection Validation**: Periodic health checks
- **Graceful Degradation**: Continues processing during outages
- **Error Logging**: Detailed connection and publishing logs

### Message Publishing
- **Queue Management**: Internal queue for reliable delivery
- **Retry Logic**: Automatic retry for failed publishes
- **Backpressure**: Handles broker congestion gracefully
- **Message Validation**: Ensures data integrity

### Common Error Scenarios
- **Broker Unavailable**: Automatic reconnection with backoff
- **Authentication Failure**: Clear error messages and retry
- **Network Issues**: Graceful handling of timeouts
- **Message Too Large**: Automatic chunking or compression

## Performance Considerations

### Network Optimization
- **Compression**: JPEG compression for images
- **Sampling**: Rate limiting for high-frequency data
- **Batch Publishing**: Efficient message batching
- **Connection Pooling**: Reuse connections when possible

### Memory Management
- **Streaming**: No large data buffering
- **Garbage Collection**: Automatic cleanup of temporary data
- **Memory Limits**: Configurable queue sizes
- **Resource Monitoring**: Built-in memory usage tracking

### Broker Load
- **QoS Selection**: Choose appropriate QoS levels
- **Retention Policy**: Minimize retained messages
- **Topic Structure**: Efficient topic hierarchy
- **Message Size**: Optimize payload sizes

## Security Considerations

### Authentication
- **Username/Password**: Basic MQTT authentication
- **TLS/SSL**: Encrypted connections (port 8883)
- **Client Certificates**: Certificate-based authentication
- **Access Control**: Broker-level topic permissions

### Data Privacy
- **Image Anonymization**: Remove sensitive data before publishing
- **Field Filtering**: Publish only necessary data fields
- **Encryption**: Use TLS for data in transit
- **Access Logging**: Monitor data access patterns

## Troubleshooting

### Common Issues

#### Connection Problems
1. Check broker hostname and port
2. Verify network connectivity
3. Validate authentication credentials
4. Check firewall settings

#### Publishing Issues
1. Verify topic mapping syntax
2. Check message size limits
3. Validate QoS settings
4. Monitor broker capacity

#### Data Format Issues
1. Check serialization compatibility
2. Validate JSON structure
3. Verify image encoding
4. Test with simple data first

### Debug Configuration
```python
import logging
logging.basicConfig(level=logging.DEBUG)

# Enable MQTT debugging
export DEBUG_MQTT=true
```

### Monitoring and Logging
- **Connection Status**: Monitor broker connectivity
- **Publish Rates**: Track message throughput
- **Error Rates**: Monitor failed publishes
- **Message Sizes**: Track payload sizes

## Advanced Usage

### Ephemeral Sources for Non-Blocking Processing

The MQTT-out filter supports **ephemeral sources** using the `?` and `??` syntax. This is particularly useful for monitoring, metrics collection, and side-channel processing without affecting the main pipeline performance.

#### Single Ephemeral (`?`)
```python
Filter.run_multi([
    # ... other filters above
    (MQTTOut, dict(
        sources='tcp://localhost:5550?;main',  # Single ? for ephemeral connection
        outputs='mqtt://localhost:1883/monitoring',
        mappings=['main/data > status!qos=2'],
        interval=5,  # Sample every 5 seconds
    )),
])
```

**Behavior:**
- Does **not participate** in frame synchronization
- Can request frames without blocking the main pipeline
- Messages may be dropped if processing is too slow
- Perfect for monitoring, logging, or side-channel analysis

#### Doubly Ephemeral (`??`)
```python
Filter.run_multi([
    # ... other filters above
    (MQTTOut, dict(
        sources=[
            'tcp://localhost:6550?? ; _metrics > m_vidin',     # Doubly ephemeral for metrics
            'tcp://localhost:6560?? ; _metrics > m_split',     # No upstream notification
            'tcp://localhost:5550?? ; main > frames!qos=0',    # Silent monitoring
        ],
        outputs='mqtt://localhost:1883/metrics',
        mappings=[
            'm_vidin/data > m_vidin',
            'm_split/data > m_split', 
            'frames/data > frames',
        ],
        interval=10,  # Sample every 10 seconds
    )),
])
```

**Behavior:**
- **Silent listener** - doesn't even notify upstream of its existence
- No flow control or synchronization
- Ideal for metrics collection, debugging, or passive monitoring
- Never affects upstream filter performance

#### Use Cases

**1. Metrics Collection**
```python
# Collect system metrics without affecting video processing
Filter.run_multi([
    # ... other filters above
    (MQTTOut, dict(
        sources='tcp://localhost:5550??;_metrics',  # Silent metrics collection
        outputs='mqtt://localhost:1883/system',
        mappings=['_metrics/data > metrics!retain=true'],
        interval=5,
    )),
])
```

**2. Side-Channel Analysis**
```python
# Process expensive AI analysis without slowing main pipeline
Filter.run_multi([
    # ... other filters above
    (MQTTOut, dict(
        sources='tcp://localhost:5550?;main',  # Ephemeral for slow processing
        outputs='mqtt://localhost:1883/analysis',
        mappings=['main/image > ai_input!qos=0'],
        interval=2,  # Lower frequency to handle slow processing
    )),
])
```

**3. Debug Monitoring**
```python
# Monitor pipeline without affecting production flow
Filter.run_multi([
    # ... other filters above
    (MQTTOut, dict(
        sources='tcp://localhost:5550??;*',  # Silent monitoring of all topics
        outputs='mqtt://localhost:1883/debug',
        mappings=[
            '*/data > debug_data!qos=0',
            '*/image > debug_frames!qos=0',
        ],
        interval=1,  # High frequency for debugging
    )),
])
```

### Custom Serialization
```python
# The filter automatically handles:
# - Nested dictionaries
# - Arrays and lists
# - Binary data (base64)
# - Images (JPEG + base64)
# - Datetime objects (ISO format)
# - NumPy arrays
```

### Dynamic Topic Mapping
```python
# Topic mapping can be dynamic based on frame data:
mappings = [
    'main/data/camera_id > cameras/{camera_id}/status',
    'main/data/sensor_type > sensors/{sensor_type}/data',
]
```

### Integration with IoT Platforms
```python
# Compatible with:
# - AWS IoT Core
# - Azure IoT Hub
# - Google Cloud IoT Core
# - Eclipse Mosquitto
# - HiveMQ
# - VerneMQ
```

## API Reference

### MQTTOutConfig
```python
class MQTTOutConfig(FilterConfig):
    class Mapping(adict):
        class Options(adict):
            qos: int | None
            retain: bool | None

        dst_topic: str
        src_topic: str | None
        src_path: list[str] | None
        options: Options | None

    mappings: str | list[str | Mapping]
    broker_host: str | None
    broker_port: int | None
    username: str | None
    password: str | None
    client_id: str | Literal[True] | None
    keepalive: int | None
    base_topic: str | None
    interval: float | None
    qos: int | None
    retain: bool | None
```

### MQTTOut
```python
class MQTTOut(Filter):
    FILTER_TYPE = 'Output'
    VALID_OPTIONS = ('qos', 'retain')
    
    @classmethod
    def normalize_config(cls, config)
    def get_client(self)
    def setup(self, config)
    def shutdown(self)
    def process(self, frames)
```

### Environment Variables
- `DEBUG_MQTT`: Enable MQTT debug logging
- `MQTT_RECONNECT_IVL`: Initial reconnect interval (seconds)
- `MQTT_RECONNECT_IVL_MAX`: Maximum reconnect interval (seconds)
- `FILTER_BROKER_HOST`: MQTT broker hostname
- `FILTER_BROKER_PORT`: MQTT broker port
- `FILTER_BASE_TOPIC`: Base MQTT topic prefix
