# Web Viewer Filter

The Web Viewer filter is an output filter for OpenFilter that provides a web-based visualization of incoming image streams. It hosts a FastAPI application that serves JPEG-encoded frames via a multipart/x-mixed-replace stream, accessible through a web browser. The filter also provides a `/data` endpoint for streaming frame metadata, making it ideal for real-time monitoring and debugging of OpenFilter pipelines.

## Overview

The Web Viewer filter is designed to handle web-based visualization scenarios where you need to:
- Display real-time image streams in a web browser
- Monitor OpenFilter pipeline output visually
- Debug image processing results
- Provide live visualization for multiple topics
- Stream frame metadata alongside images
- Host a web interface for pipeline monitoring
- Support multiple concurrent viewers
- Integrate with existing web applications

## Key Features

- **Web-based Visualization**: Real-time image display in web browsers
- **Multipart Streaming**: Efficient JPEG streaming via multipart/x-mixed-replace
- **Metadata Streaming**: Frame data streaming via `/data` endpoint
- **Multi-topic Support**: Display images from multiple topics
- **Concurrent Viewers**: Support multiple simultaneous viewers
- **FastAPI Integration**: Modern web framework with automatic API documentation
- **CORS Support**: Cross-origin resource sharing for web integration
- **Responsive Design**: Works on desktop and mobile browsers

## Configuration

### Basic Configuration

```python
from openfilter.filter_runtime.filter import Filter
from openfilter.filter_runtime.filters.webvis import Webvis

# Simple web visualization
Filter.run_multi([
    # ... other filters above
    (Webvis, dict(
        sources='tcp://localhost:5550',
        outputs='tcp://*:5552',
        port=8000,
    )),
])
```

### Advanced Configuration with Multiple Options

```python
# Web visualization with available options
Filter.run_multi([
    # ... other filters above
    (Webvis, dict(
        sources='tcp://localhost:5550',
        outputs='tcp://*:5552',
        port=8000,
        host='0.0.0.0',        # Listen on all interfaces
        enable_json=True,      # Subject data in JSON format
        sleep_interval=0.1,    # Sleep in seconds before sending subject data
    )),
])
```

### Environment Variables

You can configure via environment variables:

```bash
export FILTER_SOURCES="tcp://localhost:5550"
export FILTER_OUTPUTS="tcp://*:5552"
export FILTER_PORT="8000"
export FILTER_HOST="0.0.0.0"
export FILTER_ENABLE_JSON="true"
export FILTER_SLEEP_INTERVAL="0.1"
```

## Web Interface

### Main Visualization Page

The Web Viewer filter provides a web interface accessible at:

```
http://localhost:8000/
```

#### Page Features
- **Real-time Image Display**: Shows incoming images as they arrive
- **Topic Selection**: Dropdown to select different topics
- **Metadata Display**: Shows frame information and statistics
- **Responsive Layout**: Adapts to different screen sizes
- **Auto-refresh**: Automatically updates with new frames


### Image Streaming Endpoint

#### Topic Endpoint (`/{topic}`)
Provides real-time image streaming for specific topics:

```
GET /
GET /main
GET /camera1
```

#### Stream Features
- **Multipart/x-mixed-replace**: Standard MJPEG streaming format
- **Topic-based URLs**: Direct topic access via URL path
- **JPEG Encoding**: Efficient image compression
- **Real-time Updates**: Immediate frame updates
- **Browser Compatibility**: Works with all modern browsers

#### Stream Examples
```bash
# Stream main topic (default)
curl -N http://localhost:8000/

# Stream main topic explicitly
curl -N http://localhost:8000/main

# Stream camera1 topic
curl -N http://localhost:8000/camera1
```

### Data Streaming Endpoint

#### Data Endpoint (`/{topic}/data`)
Provides frame metadata streaming for specific topics:

```
GET /main/data
GET /camera1/data
```

#### Data Features
- **Server-Sent Events**: Real-time data streaming via text/event-stream
- **JSON Data**: Frame data dictionary as JSON string
- **Topic-based URLs**: Data from specific topics via URL path
- **Event Stream**: Real-time data updates every second
- **API Integration**: Easy integration with web applications

#### Data Format
The `/data` endpoint streams Server-Sent Events with the following format:
```
data: {'meta': {'id': 231, 'ts': 1758745938.571617, 'src': 'file://./data/video-03.mp4', 'src_fps': 25.0, 'detections': [{'class': 'face', 'rois': [421, 133, 503, 236], 'confidence': 0.9186320304870605}, {'class': 'face', 'rois': [754, 8, 826, 132], 'confidence': 0.9028760194778442}]}, 'faces_detected': 2, 'face_coordinates': [{'bbox': [421, 133, 82, 103], 'confidence': 0.9186320304870605}, {'bbox': [754, 8, 72, 124], 'confidence': 0.9028760194778442}], 'face_details': [{'face_id': 0, 'bounding_box': {'x': 421, 'y': 133, 'width': 82, 'height': 103}, 'center': {'x': 462, 'y': 184}, 'confidence': 0.9186320304870605}, {'face_id': 1, 'bounding_box': {'x': 754, 'y': 8, 'width': 72, 'height': 124}, 'center': {'x': 790, 'y': 70}, 'confidence': 0.9028760194778442}]}

```

#### Data Examples
```bash
# Stream main topic data
curl -N http://localhost:8000/main/data
# Response: Server-Sent Events with JSON frame data

# Stream camera1 topic data  
curl -N http://localhost:8000/camera1/data
# Response: Server-Sent Events with JSON frame data
```


## Topic Management

The Web Viewer filter automatically creates endpoints for any topics that receive data. Topics are discovered dynamically from incoming frames - you cannot configure which topics to include or exclude.


## Usage Examples

### Example 1: Basic Web Visualization
```python
Filter.run_multi([
    # ... other filters above
    (VideoIn, dict(
        sources='file:///input.mp4',
        outputs='tcp://*:5550',
    )),
    (ObjectDetection, dict(
        sources='tcp://localhost:5550',
        outputs='tcp://*:5552',
    )),
    (Webvis, dict(
        sources='tcp://localhost:5552',
        outputs='tcp://*:5554',
        port=8000,
    )),
])
```

**Behavior:** Displays object detection results in web browser at `http://localhost:8000`.

### Example 2: Multi-Camera Monitoring
```python
Filter.run_multi([
    # ... other filters above
    (VideoIn, dict(
        sources='0',  # Camera 1
        outputs='tcp://*:5550',
    )),
    (VideoIn, dict(
        sources='1',  # Camera 2
        outputs='tcp://*:5552',
    )),
    (Webvis, dict(
        sources=[
            'tcp://localhost:5550', 
            # need to remap the topic, cause 1 main topic is accepted
            'tcp://localhost:5552;>camera2'], 
        outputs='tcp://*:5554',
        port=8000,
    )),
])
```

**Behavior:** Monitors multiple cameras with topic selection in web interface.

### Example 3: Real-time Processing Visualization
```python
Filter.run_multi([
    # ... other filters above
    (VideoIn, dict(
        sources='rtsp://camera.local/stream',
        outputs='tcp://*:5550',
    )),
    (FaceDetection, dict(
        sources='tcp://localhost:5550',
        outputs='tcp://*:5552',
    )),
    (Webvis, dict(
        sources='tcp://localhost:5552',
        outputs='tcp://*:5554',
        port=8000,
    )),
])
```

**Behavior:** Shows face detection results with metadata streaming.

### Example 4: Debugging and Development
```python
Filter.run_multi([
    # ... other filters above
    (ImageIn, dict(
        sources='file:///images/',
        outputs='tcp://*:5550',
    )),
    (Util, dict(
        sources='tcp://localhost:5550',
        outputs='tcp://*:5552',
        log=True,  # Log frame data
    )),
    (Webvis, dict(
        sources='tcp://localhost:5552',
        outputs='tcp://*:5554',
        port=8000,
    )),
])
```

**Behavior:** Provides debugging interface with logged data visualization.

### Example 5: Production Monitoring
```python
Filter.run_multi([
    # ... other filters above
    (VideoIn, dict(
        sources='rtsp://production-camera.local/stream',
        outputs='tcp://*:5550',
    )),
    (ProductionProcessor, dict(
        sources='tcp://localhost:5550',
        outputs='tcp://*:5552',
    )),
    (Webvis, dict(
        sources='tcp://localhost:5552',
        outputs='tcp://*:5554',
        port=8000,
        host='0.0.0.0',  # Listen on all interfaces
    )),
])
```

**Behavior:** Production monitoring accessible from any network location.

### Example 6: API Integration
```python
Filter.run_multi([
    # ... other filters above
    (VideoIn, dict(
        sources='0',  # Webcam
        outputs='tcp://*:5550',
    )),
    (Webvis, dict(
        sources='tcp://localhost:5550',
        outputs='tcp://*:5552',
        port=8000,
    )),
])
```


## API Endpoints

### Available Endpoints

#### 1. Root Endpoint (`/`)
- **Method**: GET
- **Purpose**: Main web interface
- **Response**: HTML page with visualization

#### 2. Topic Stream Endpoint (`/{topic}` or `/api/{topic}`)
- **Method**: GET
- **Purpose**: Image streaming for a specific topic (or the default topic via `/` or `/api`)
- **Parameters**: `topic` in URL path
- **Response**: multipart/x-mixed-replace JPEG stream
- **Aliases**: `/api` (streams the default topic) and `/api/{topic}` (streams a specific topic). Namespacing under `/api/{topic}` provides a clean route structure and avoids collisions with reserved words.


#### 3. Topic Data Endpoint (`/{topic}/data`)
- **Method**: GET
- **Purpose**: Frame metadata streaming for specific topic
- **Parameters**: `topic` in URL path
- **Response**: text/event-stream data

#### 4. Snapshot Endpoint (`/snapshot` or `/{topic}/snapshot`)
- **Method**: GET
- **Purpose**: Retrieve the latest single JPEG frame snapshot for a given topic
- **Parameters**: Optional `topic` in URL path (can also be namespaced under `/api/snapshot` or `/api/snapshot/{topic}`)
- **Response**: `image/jpeg` binary content of the latest frame. Returns `404` if no frame has been received yet.

#### 5. Snapshot Payload Endpoint (`/snapshot-payload` or `/{topic}/snapshot-payload`)
- **Method**: GET
- **Purpose**: Retrieve the latest JPEG frame snapshot along with its associated metadata packed into HTTP response headers
- **Parameters**: Optional `topic` in URL path (can also be namespaced under `/api/snapshot-payload` or `/api/snapshot-payload/{topic}`)
- **Response**: `image/jpeg` binary content of the latest frame, plus custom HTTP headers:
  - `X-Topic`: The URL-encoded topic name.
  - `X-Metadata`: The URL-encoded JSON string representation of the frame's metadata.
  - `X-Timestamp`: The server epoch time when the snapshot response was generated.
  - `X-Width` / `X-Height` / `X-Format`: Dimensions and color format of the frame.
- **Header Size Limits**: Note that HTTP response headers are subject to size constraints (typically 8–16KB depending on proxies and web servers). For highly complex frame metadata (e.g., many detections), clients should poll `/snapshot` and `/latest-data` separately to avoid header truncation or rejection.

#### 6. Latest Data Endpoint (`/latest-data` or `/{topic}/latest-data`)
- **Method**: GET
- **Purpose**: Retrieve the latest frame metadata as a static JSON payload
- **Parameters**: Optional `topic` in URL path (can also be namespaced under `/api/latest-data` or `/api/latest-data/{topic}`)
- **Response**: `application/json` payload containing the latest metadata dictionary.

### Reserved Topic Names

> [!WARNING]
> The names `snapshot`, `snapshot-payload`, `latest-data`, and `api` are reserved keyword paths used by the Web Viewer filter's static endpoints.
> If a pipeline topic is literally named one of these reserved words, its bare route (e.g., `/{topic}`) is shadowed by the static endpoint.
> To ensure the live video stream remains accessible for a topic with one of these names, clients must use the namespaced stream alias:
> - **Reserved Topic `snapshot`**: Stream at `/api/snapshot` (instead of `/snapshot` which returns a single JPEG snapshot)
> - **Reserved Topic `snapshot-payload`**: Stream at `/api/snapshot-payload` (instead of `/snapshot-payload` which returns snapshot with headers)
> - **Reserved Topic `latest-data`**: Stream at `/api/latest-data` (instead of `/latest-data` which returns static metadata JSON)
> - **Reserved Topic `api`**: Stream at `/api/api` (instead of `/api` which streams the default topic)

### API Examples

#### Stream Images
```bash
curl -N http://localhost:8000/main
# Response: multipart/x-mixed-replace JPEG stream

curl -N http://localhost:8000/camera1
# Response: multipart/x-mixed-replace JPEG stream

# Or stream via namespaced aliases (recommended for reserved topic names)
curl -N http://localhost:8000/api/main
curl -N http://localhost:8000/api/camera1
```

#### Stream Data
```bash
curl -N http://localhost:8000/main/data
# Response: text/event-stream data

curl -N http://localhost:8000/camera1/data
# Response: text/event-stream data
```

#### Fetch Snapshot & Latest Data (Polling)
```bash
# Get raw snapshot image
curl -o snapshot.jpg http://localhost:8000/main/snapshot

# Get snapshot image with metadata packed in headers
curl -v http://localhost:8000/main/snapshot-payload > snapshot_with_headers.jpg

# Get latest metadata JSON payload
curl http://localhost:8000/main/latest-data
```

## CORS Configuration

The Web Viewer filter has CORS (Cross-Origin Resource Sharing) hardcoded to allow all origins (`*`). This cannot be configured - all web requests from any domain are allowed by default.

## Performance Considerations

### Web Server Performance
- **Concurrent Connections**: FastAPI handles multiple viewers
- **Memory Usage**: Image buffering for multiple viewers
- **CPU Usage**: JPEG encoding for each viewer
- **Network Bandwidth**: Multiple concurrent streams

### Image Processing Performance
- **JPEG Quality**: Balance between quality and size
- **Frame Rate**: Limit frame rate for web display
- **Resolution**: Optimize resolution for web viewing
- **Compression**: Efficient JPEG compression

### Optimization Strategies
```python
# Optimize for web performance
Filter.run_multi([
    # ... other filters above
    (VideoIn, dict(
        sources='file:///input.mp4',
        outputs='tcp://*:5550',
    )),
    (Util, dict(
        sources='tcp://localhost:5550',
        outputs='tcp://*:5552',
        resize='800x600',  # Smaller images for web
        maxfps=15,         # Lower frame rate
    )),
    (Webvis, dict(
        sources='tcp://localhost:5552',
        outputs='tcp://*:5554',
        port=8000,
    )),
])
```

## Error Handling

### Common Error Scenarios
- **Port Conflicts**: Port already in use
- **Image Processing Errors**: Failed image encoding
- **Network Issues**: Connection failures
- **Memory Issues**: Insufficient memory for buffering
- **Browser Compatibility**: Unsupported browser features

### Error Recovery
- **Automatic Retry**: Retries failed operations
- **Graceful Degradation**: Continues with available functionality
- **Error Logging**: Logs errors for debugging
- **Resource Cleanup**: Proper cleanup on failures

### Error Examples
```python
# Port already in use
port=8000  # Error: Port 8000 already in use

# Invalid host binding
host='invalid'  # Error: Invalid host address

# CORS configuration error
# CORS cannot be configured - it's hardcoded
```

## Debugging and Monitoring

### Debug Configuration
```python
import logging
logging.basicConfig(level=logging.DEBUG)

# Enable webvis debugging
export DEBUG_WEBVIS=true
export LOG_LEVEL=DEBUG
```

### Debug Information
- **Web Server Status**: Shows server startup and status
- **Connection Information**: Logs client connections
- **Image Processing**: Logs image encoding operations
- **Error Details**: Detailed error information

### Monitoring
- **Active Connections**: Track number of active viewers
- **Frame Rates**: Monitor actual vs. target frame rates
- **Error Rates**: Track connection and processing errors
- **Resource Usage**: Monitor memory and CPU usage

## Troubleshooting

### Common Issues

#### Web Server Issues
1. Check port availability
2. Verify host binding
3. Check firewall settings
4. Validate configuration parameters

#### Image Display Issues
1. Check image format support
2. Verify JPEG encoding
3. Monitor frame rate
4. Check browser compatibility

#### Network Issues
1. Check network connectivity
2. Verify CORS configuration
3. Monitor bandwidth usage
4. Test with different browsers

#### Performance Issues
1. Optimize image resolution
2. Reduce frame rate
3. Monitor resource usage
4. Check concurrent connections

### Debug Configuration
```python
# Enable comprehensive debugging
Filter.run_multi([
    # ... other filters above
    (Webvis, dict(
        sources='tcp://localhost:5550',
        outputs='tcp://*:5552',
        port=8000,
    )),
])
```

## Advanced Usage

### Custom Web Interface
```python
# Custom web interface integration
Filter.run_multi([
    # ... other filters above
    (Webvis, dict(
        sources='tcp://localhost:5550',
        outputs='tcp://*:5552',
        port=8000,
    )),
])
```

### Multi-Stream Integration
```python
# Multiple web visualization instances
Filter.run_multi([
    # ... other filters above
    (VideoIn, dict(
        sources='0',  # Camera 1
        outputs='tcp://*:5550',
    )),
    (VideoIn, dict(
        sources='1',  # Camera 2
        outputs='tcp://*:5552',
    )),
    (Webvis, dict(
        sources='tcp://localhost:5550',
        outputs='tcp://*:5554',
        port=8000,
    )),
    (Webvis, dict(
        sources='tcp://localhost:5552',
        outputs='tcp://*:5556',
        port=8081,
    )),
])
```

### API Integration
```python
# API integration with external systems
Filter.run_multi([
    # ... other filters above
    (Webvis, dict(
        sources='tcp://localhost:5550',
        outputs='tcp://*:5552',
        port=8000,
    )),
])
```

## API Reference

### WebvisConfig
```python
class WebvisConfig(FilterConfig):
    sources: str | list[str] | list[tuple[str, dict[str, Any]]]
    outputs: str | list[str] | list[tuple[str, dict[str, Any]]]
    port: int | None
    host: str | None
```

### Webvis
```python
class Webvis(Filter):
    FILTER_TYPE = 'Output'
    
    @classmethod
    def normalize_config(cls, config)
    def init(self, config)
    def setup(self, config)
    def shutdown(self)
    def process(self, frames)
    def create_web_app(self)
    def stream_images(self, topic)
    def stream_data(self, topic)
    def get_available_topics(self)
    def encode_image(self, frame)
```

### Environment Variables
- `FILTER_SOURCES`: Input sources
- `FILTER_OUTPUTS`: Output destinations
- `FILTER_PORT`: Web server port (default: 8000)
- `FILTER_HOST`: Web server host (default: '0.0.0.0')
