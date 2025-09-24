# Webvis Filter

The Webvis filter is an output filter for OpenFilter that provides a web-based visualization of incoming image streams. It hosts a FastAPI application that serves JPEG-encoded frames via a multipart/x-mixed-replace stream, accessible through a web browser. The filter also provides a `/data` endpoint for streaming frame metadata, making it ideal for real-time monitoring and debugging of OpenFilter pipelines.

## Overview

The Webvis filter is designed to handle web-based visualization scenarios where you need to:
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
    (Webvis, dict(
        sources='tcp://localhost:5550',
        outputs='tcp://*:5552',
        port=8000,
        host='0.0.0.0',        # Listen on all interfaces
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
```

## Web Interface

### Main Visualization Page

The webvis filter provides a web interface accessible at:

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
- **Frame Metadata**: Frame information and statistics
- **Topic-based URLs**: Data from specific topics via URL path
- **Event Stream**: Real-time data updates
- **API Integration**: Easy integration with web applications

#### Data Examples
```bash
# Stream main topic data
curl -N http://localhost:8000/main/data

# Stream camera1 topic data
curl -N http://localhost:8000/camera1/data
```

## Topic Management

The webvis filter automatically creates endpoints for any topics that receive data. Topics are discovered dynamically from incoming frames - you cannot configure which topics to include or exclude.


## Usage Examples

### Example 1: Basic Web Visualization
```python
Filter.run_multi([
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

#### 2. Topic Stream Endpoint (`/{topic}`)
- **Method**: GET
- **Purpose**: Image streaming for specific topic
- **Parameters**: `topic` in URL path
- **Response**: multipart/x-mixed-replace JPEG stream

#### 3. Topic Data Endpoint (`/{topic}/data`)
- **Method**: GET
- **Purpose**: Frame metadata streaming for specific topic
- **Parameters**: `topic` in URL path
- **Response**: text/event-stream data

### API Examples

#### Stream Images
```bash
curl -N http://localhost:8000/main
# Response: multipart/x-mixed-replace JPEG stream

curl -N http://localhost:8000/camera1
# Response: multipart/x-mixed-replace JPEG stream
```

#### Stream Data
```bash
curl -N http://localhost:8000/main/data
# Response: text/event-stream data

curl -N http://localhost:8000/camera1/data
# Response: text/event-stream data
```

## CORS Configuration

The webvis filter has CORS (Cross-Origin Resource Sharing) hardcoded to allow all origins (`*`). This cannot be configured - all web requests from any domain are allowed by default.

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
