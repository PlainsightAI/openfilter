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
        port=8080,
    )),
])
```

### Advanced Configuration with Multiple Options

```python
# Web visualization with comprehensive options
Filter.run_multi([
    (Webvis, dict(
        sources='tcp://localhost:5550',
        outputs='tcp://*:5552',
        port=8080,
        host='0.0.0.0',        # Listen on all interfaces
        title='Pipeline Monitor', # Custom page title
        topics=['main', 'camera1'], # Specific topics
        data_endpoint=True,     # Enable data streaming
        cors_origins=['*'],     # Allow all origins
    )),
])
```

### Environment Variables

You can configure via environment variables:

```bash
export FILTER_SOURCES="tcp://localhost:5550"
export FILTER_OUTPUTS="tcp://*:5552"
export FILTER_PORT="8080"
export FILTER_HOST="0.0.0.0"
export FILTER_TITLE="Pipeline Monitor"
export FILTER_TOPICS="main,camera1"
export FILTER_DATA_ENDPOINT="true"
export FILTER_CORS_ORIGINS="*"
```

## Web Interface

### Main Visualization Page

The webvis filter provides a web interface accessible at:

```
http://localhost:8080/
```

#### Page Features
- **Real-time Image Display**: Shows incoming images as they arrive
- **Topic Selection**: Dropdown to select different topics
- **Metadata Display**: Shows frame information and statistics
- **Responsive Layout**: Adapts to different screen sizes
- **Auto-refresh**: Automatically updates with new frames

#### Page Structure
```html
<!DOCTYPE html>
<html>
<head>
    <title>Pipeline Monitor</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        /* Responsive CSS styles */
    </style>
</head>
<body>
    <div class="container">
        <h1>Pipeline Monitor</h1>
        <div class="controls">
            <select id="topic-select">
                <option value="main">Main</option>
                <option value="camera1">Camera 1</option>
            </select>
        </div>
        <div class="image-container">
            <img id="stream-image" src="/stream?topic=main" alt="Live Stream">
        </div>
        <div class="metadata">
            <div id="frame-info">Frame: 0</div>
            <div id="timestamp">Timestamp: -</div>
            <div id="fps">FPS: 0</div>
        </div>
    </div>
    <script>
        // JavaScript for real-time updates
    </script>
</body>
</html>
```

### Image Streaming Endpoint

#### Stream Endpoint (`/stream`)
Provides real-time image streaming:

```
GET /stream?topic=main
GET /stream?topic=camera1
```

#### Stream Features
- **Multipart/x-mixed-replace**: Standard MJPEG streaming format
- **Topic Filtering**: Stream specific topics
- **JPEG Encoding**: Efficient image compression
- **Real-time Updates**: Immediate frame updates
- **Browser Compatibility**: Works with all modern browsers

#### Stream Examples
```python
# Stream main topic
curl -N http://localhost:8080/stream?topic=main

# Stream camera1 topic
curl -N http://localhost:8080/stream?topic=camera1
```

### Data Streaming Endpoint

#### Data Endpoint (`/data`)
Provides frame metadata streaming:

```
GET /data?topic=main
GET /data?topic=camera1
```

#### Data Features
- **JSON Streaming**: Real-time JSON data
- **Frame Metadata**: Frame information and statistics
- **Topic Filtering**: Data from specific topics
- **WebSocket-like**: Real-time data updates
- **API Integration**: Easy integration with web applications

#### Data Examples
```python
# Stream main topic data
curl -N http://localhost:8080/data?topic=main

# Stream camera1 topic data
curl -N http://localhost:8080/data?topic=camera1
```

## Topic Management

### Topic Configuration

#### Specific Topics
```python
topics=['main', 'camera1', 'camera2']  # Only these topics
topics=None  # All topics (default)
```

#### Topic Examples
```python
# Specific topics only
Filter.run_multi([
    (Webvis, dict(
        sources='tcp://localhost:5550',
        outputs='tcp://*:5552',
        port=8080,
        topics=['main', 'camera1'],  # Only main and camera1
    )),
])

# All topics
Filter.run_multi([
    (Webvis, dict(
        sources='tcp://localhost:5550',
        outputs='tcp://*:5552',
        port=8080,
        topics=None,  # All topics
    )),
])
```

### Topic Selection

The web interface provides topic selection:

```javascript
// Topic selection JavaScript
function updateTopic() {
    const topic = document.getElementById('topic-select').value;
    const image = document.getElementById('stream-image');
    const dataUrl = document.getElementById('data-url');
    
    image.src = `/stream?topic=${topic}`;
    dataUrl.href = `/data?topic=${topic}`;
}
```

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
        port=8080,
    )),
])
```

**Behavior:** Displays object detection results in web browser at `http://localhost:8080`.

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
        sources=['tcp://localhost:5550', 'tcp://localhost:5552'],
        outputs='tcp://*:5554',
        port=8080,
        topics=['camera1', 'camera2'],
        title='Multi-Camera Monitor',
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
        port=8080,
        data_endpoint=True,  # Enable data streaming
        title='Face Detection Monitor',
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
        port=8080,
        data_endpoint=True,
        title='Debug Monitor',
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
        port=8080,
        host='0.0.0.0',  # Listen on all interfaces
        cors_origins=['*'],  # Allow all origins
        title='Production Monitor',
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
        port=8080,
        data_endpoint=True,
        cors_origins=['http://localhost:3000'],  # React app
    )),
])
```

**Behavior:** Provides API endpoints for integration with React applications.

## Web Interface Features

### Responsive Design

The web interface adapts to different screen sizes:

```css
/* Responsive CSS */
.container {
    max-width: 1200px;
    margin: 0 auto;
    padding: 20px;
}

.image-container {
    text-align: center;
    margin: 20px 0;
}

#stream-image {
    max-width: 100%;
    height: auto;
    border: 1px solid #ccc;
}

@media (max-width: 768px) {
    .container {
        padding: 10px;
    }
    
    #stream-image {
        max-width: 100%;
    }
}
```

### Real-time Updates

JavaScript handles real-time updates:

```javascript
// Real-time update JavaScript
let frameCount = 0;
let lastUpdate = Date.now();

function updateMetadata() {
    const now = Date.now();
    const fps = frameCount / ((now - lastUpdate) / 1000);
    
    document.getElementById('fps').textContent = `FPS: ${fps.toFixed(1)}`;
    document.getElementById('frame-info').textContent = `Frame: ${frameCount}`;
    
    frameCount++;
    lastUpdate = now;
}

// Update metadata every second
setInterval(updateMetadata, 1000);
```

### Topic Selection

Dynamic topic selection:

```javascript
// Topic selection
function loadTopics() {
    fetch('/topics')
        .then(response => response.json())
        .then(topics => {
            const select = document.getElementById('topic-select');
            select.innerHTML = '';
            
            topics.forEach(topic => {
                const option = document.createElement('option');
                option.value = topic;
                option.textContent = topic;
                select.appendChild(option);
            });
        });
}

// Load topics on page load
document.addEventListener('DOMContentLoaded', loadTopics);
```

## API Endpoints

### Available Endpoints

#### 1. Root Endpoint (`/`)
- **Method**: GET
- **Purpose**: Main web interface
- **Response**: HTML page with visualization

#### 2. Stream Endpoint (`/stream`)
- **Method**: GET
- **Purpose**: Image streaming
- **Parameters**: `topic` (optional)
- **Response**: multipart/x-mixed-replace JPEG stream

#### 3. Data Endpoint (`/data`)
- **Method**: GET
- **Purpose**: Frame metadata streaming
- **Parameters**: `topic` (optional)
- **Response**: JSON data stream

#### 4. Topics Endpoint (`/topics`)
- **Method**: GET
- **Purpose**: List available topics
- **Response**: JSON array of topic names

#### 5. Health Endpoint (`/health`)
- **Method**: GET
- **Purpose**: Health check
- **Response**: JSON status

### API Examples

#### Get Available Topics
```bash
curl http://localhost:8080/topics
# Response: ["main", "camera1", "camera2"]
```

#### Stream Images
```bash
curl -N http://localhost:8080/stream?topic=main
# Response: multipart/x-mixed-replace JPEG stream
```

#### Stream Data
```bash
curl -N http://localhost:8080/data?topic=main
# Response: JSON data stream
```

#### Health Check
```bash
curl http://localhost:8080/health
# Response: {"status": "healthy", "topics": ["main", "camera1"]}
```

## CORS Configuration

### Cross-Origin Resource Sharing

Configure CORS for web integration:

```python
# Allow all origins
cors_origins=['*']

# Specific origins
cors_origins=['http://localhost:3000', 'https://myapp.com']

# No CORS (default)
cors_origins=None
```

### CORS Examples
```python
# React app integration
Filter.run_multi([
    (Webvis, dict(
        sources='tcp://localhost:5550',
        outputs='tcp://*:5552',
        port=8080,
        cors_origins=['http://localhost:3000'],  # React dev server
    )),
])

# Production web app
Filter.run_multi([
    (Webvis, dict(
        sources='tcp://localhost:5550',
        outputs='tcp://*:5552',
        port=8080,
        cors_origins=['https://myapp.com'],  # Production domain
    )),
])
```

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
        port=8080,
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
port=8080  # Error: Port 8080 already in use

# Invalid host binding
host='invalid'  # Error: Invalid host address

# CORS configuration error
cors_origins=['invalid']  # Error: Invalid CORS origin
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
        port=8080,
        data_endpoint=True,  # Enable data streaming
        cors_origins=['*'],  # Allow all origins for testing
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
        port=8080,
        cors_origins=['http://localhost:3000'],  # Custom app
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
        port=8080,
        title='Camera 1 Monitor',
    )),
    (Webvis, dict(
        sources='tcp://localhost:5552',
        outputs='tcp://*:5556',
        port=8081,
        title='Camera 2 Monitor',
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
        port=8080,
        data_endpoint=True,  # Enable data API
        cors_origins=['https://myapp.com'],  # Production domain
    )),
])
```

## API Reference

### WebvisConfig
```python
class WebvisConfig(FilterConfig):
    sources: str | list[str] | list[tuple[str, dict[str, Any]]]
    outputs: str | list[str] | list[tuple[str, dict[str, Any]]]
    port: int
    host: str | None
    title: str | None
    topics: list[str] | None
    data_endpoint: bool | None
    cors_origins: list[str] | None
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
- `DEBUG_WEBVIS`: Enable debug logging
- `FILTER_SOURCES`: Input sources
- `FILTER_OUTPUTS`: Output destinations
- `FILTER_PORT`: Web server port
- `FILTER_HOST`: Web server host
- `FILTER_TITLE`: Web page title
- `FILTER_TOPICS`: Target topics
- `FILTER_DATA_ENDPOINT`: Enable data streaming
- `FILTER_CORS_ORIGINS`: CORS allowed origins
