# Video Source Filter

The Video Source filter is an input filter for OpenFilter that reads video streams from various sources including files, webcams, and network streams (RTSP, HTTP, S3). It supports various video processing options like BGR/RGB conversion, synchronization modes, looping, FPS control, and image resizing. The filter uses the `vidgear` library for robust video capture and processing.

## Overview

The Video Source filter is designed to handle video input scenarios where you need to:
- Read video files from local storage or cloud storage (S3)
- Capture video from webcams and USB cameras
- Stream video from network sources (RTSP, HTTP)
- Control video playback parameters (FPS, looping, synchronization)
- Apply image transformations (resize, format conversion)
- Handle various video formats and codecs
- Process video streams in real-time or batch mode

## Key Features

- **Multiple Input Sources**: Files, webcams, RTSP, HTTP, S3
- **Video Format Support**: Various codecs and containers
- **Real-time Processing**: Live video stream processing
- **Synchronization Control**: Frame synchronization options
- **Looping Support**: Continuous video playback
- **FPS Control**: Configurable frame rate output
- **Image Resizing**: Dynamic image size adjustment
- **Format Conversion**: BGR/RGB color space conversion
- **Error Recovery**: Robust error handling and recovery

## Configuration

### Basic Configuration

```python
from openfilter.filter_runtime.filter import Filter
from openfilter.filter_runtime.filters.video_in import VideoIn

# Simple video file input
Filter.run_multi([
    # ... other filters above
    (VideoIn, dict(
        sources='file:///path/to/video.mp4',
        outputs='tcp://*:5550',
    )),
])
```

### Advanced Configuration with Multiple Options

```python
# Video input with comprehensive options
Filter.run_multi([
    # ... other filters above
    (VideoIn, dict(
        sources='file:///path/to/video.mp4',
        outputs='tcp://*:5550',
        bgr=True,           # BGR color format
        sync=True,          # Enable synchronization
        loop=True,          # Loop video playback
        fps=30,             # Output 30 FPS
        maxsize='1920x1080', # Maximum size
        resize='800x600',   # Resize to specific dimensions
    )),
])
```

### Environment Variables

You can configure via environment variables:

```bash
export FILTER_SOURCES="file:///path/to/video.mp4"
export FILTER_OUTPUTS="tcp://*:5550"
export FILTER_BGR="true"
export FILTER_SYNC="true"
export FILTER_LOOP="true"
export FILTER_FPS="30"
export FILTER_MAXSIZE="1920x1080"
export FILTER_RESIZE="800x600"
```

## Input Sources

### 1. Local Video Files

#### File Path Format
```python
sources='file:///path/to/video.mp4'
sources='file:///path/to/video.avi'
sources='file:///path/to/video.mov'
```

#### Supported Formats
- **MP4**: H.264, H.265, MPEG-4
- **AVI**: Various codecs
- **MOV**: QuickTime format
- **MKV**: Matroska format
- **WMV**: Windows Media Video
- **FLV**: Flash Video
- **WebM**: WebM format

#### File Examples
```python
# Local file input
Filter.run_multi([
    # ... other filters above
    (VideoIn, dict(
        sources='file:///home/user/videos/sample.mp4',
        outputs='tcp://*:5550',
    )),
])
```

### 2. Webcam and USB Camera

#### Camera URL Format
```python
sources='webcam://0'        # Default camera
sources='webcam://1'        # Second camera
sources='webcam://2'        # Third camera
```

#### Camera Examples
```python
# Webcam input
Filter.run_multi([
    # ... other filters above
    (VideoIn, dict(
        sources='webcam://0',  # Default webcam
        outputs='tcp://*:5550',
        fps=30,
    )),
])

# Multiple cameras
Filter.run_multi([
    # ... other filters above
    (VideoIn, dict(
        sources='webcam://0',  # Camera 1
        outputs='tcp://*:5550',
    )),
    (VideoIn, dict(
        sources='webcam://1',  # Camera 2
        outputs='tcp://*:5552',
    )),
])
```

### 3. Network Streams (RTSP)

#### RTSP URL Format
```python
sources='rtsp://username:password@ip:port/path'
sources='rtsp://192.168.1.100:554/stream1'
```

#### RTSP Examples
```python
# IP camera stream
Filter.run_multi([
    # ... other filters above
    (VideoIn, dict(
        sources='rtsp://admin:password@192.168.1.100:554/stream1',
        outputs='tcp://*:5550',
        sync=True,  # Important for network streams
    )),
])

# Multiple RTSP streams
Filter.run_multi([
    # ... other filters above
    (VideoIn, dict(
        sources='rtsp://camera1.local/stream',
        outputs='tcp://*:5550',
    )),
    (VideoIn, dict(
        sources='rtsp://camera2.local/stream',
        outputs='tcp://*:5552',
    )),
])
```

### 4. HTTP Streams

#### HTTP URL Format
```python
sources='http://server:port/stream'
sources='https://server:port/stream'
```

#### HTTP Examples
```python
# HTTP video stream
Filter.run_multi([
    # ... other filters above
    (VideoIn, dict(
        sources='http://192.168.1.100:8080/video',
        outputs='tcp://*:5550',
    )),
])

# HTTPS stream
Filter.run_multi([
    # ... other filters above
    (VideoIn, dict(
        sources='https://streaming.server.com/live',
        outputs='tcp://*:5550',
    )),
])
```

### 5. Cloud Storage (S3)

#### S3 URL Format
```python
sources='s3://bucket/path/to/video.mp4'
sources='s3://my-bucket/videos/sample.mp4'
```

#### S3 Examples
```python
# S3 video file
Filter.run_multi([
    # ... other filters above
    (VideoIn, dict(
        sources='s3://my-video-bucket/sample.mp4',
        outputs='tcp://*:5550',
        loop=True,  # Loop for continuous processing
    )),
])
```

## Video Processing Options

### Color Format (`bgr`)

Controls the color format of output images:

```python
bgr=True   # BGR format (default for OpenCV)
bgr=False  # RGB format (default for many ML frameworks)
```

#### Color Format Examples
```python
# BGR format for OpenCV processing
Filter.run_multi([
    # ... other filters above
    (VideoIn, dict(
        sources='file:///video.mp4',
        outputs='tcp://*:5550',
        bgr=True,
    )),
    (OpenCVProcessor, dict(
        sources='tcp://localhost:5550',
        outputs='tcp://*:5552',
    )),
])
```

### Synchronization (`sync`)

Controls frame synchronization:

```python
sync=True   # Enable synchronization (recommended for network streams)
sync=False  # Disable synchronization (faster processing)
```

#### Synchronization Use Cases
- **Network Streams**: Essential for RTSP/HTTP streams
- **Real-time Processing**: Maintains timing accuracy
- **Multi-camera**: Synchronizes multiple camera streams
- **Performance**: Can impact processing speed

### Looping (`loop`)

Controls video playback looping:

```python
loop=True   # Loop video playback
loop=False  # Play once (default)
```

#### Looping Examples
```python
# Continuous video processing
Filter.run_multi([
    # ... other filters above
    (VideoIn, dict(
        sources='file:///short_video.mp4',
        outputs='tcp://*:5550',
        loop=True,  # Loop for continuous processing
    )),
    (ObjectDetection, dict(
        sources='tcp://localhost:5550',
        outputs='tcp://*:5552',
    )),
])
```

### Frame Rate Control (`fps`)

Controls output frame rate:

```python
fps=30      # 30 FPS output
fps=60      # 60 FPS output
fps=None    # Original video FPS (default)
```

#### FPS Control Examples
```python
# Reduce frame rate for performance
Filter.run_multi([
    # ... other filters above
    (VideoIn, dict(
        sources='file:///high_fps_video.mp4',
        outputs='tcp://*:5550',
        fps=15,  # Reduce to 15 FPS
    )),
    (ImageProcessor, dict(
        sources='tcp://localhost:5550',
        outputs='tcp://*:5552',
    )),
])
```

### Image Resizing

#### Maximum Size (`maxsize`)
Limits maximum image dimensions:

```python
maxsize='1920x1080'  # Maximum 1920x1080
maxsize='1280x720'   # Maximum 1280x720
maxsize=None         # No size limit (default)
```

#### Specific Resize (`resize`)
Resizes to specific dimensions:

```python
resize='800x600'     # Resize to 800x600
resize='640x480'     # Resize to 640x480
resize=None          # No resize (default)
```

#### Resize Examples
```python
# Resize for performance
Filter.run_multi([
    # ... other filters above
    (VideoIn, dict(
        sources='file:///4k_video.mp4',
        outputs='tcp://*:5550',
        resize='1280x720',  # Resize to HD
    )),
    (ObjectDetection, dict(
        sources='tcp://localhost:5550',
        outputs='tcp://*:5552',
    )),
])
```

## Usage Examples

### Example 1: Basic Video File Processing
```python
Filter.run_multi([
    # ... other filters above
    (VideoIn, dict(
        sources='file:///path/to/video.mp4',
        outputs='tcp://*:5550',
    )),
    (ObjectDetection, dict(
        sources='tcp://localhost:5550',
        outputs='tcp://*:5552',
    )),
    (ImageOut, dict(
        sources='tcp://localhost:5552',
        outputs='file:///output/detected_{frame_number}.jpg',
    )),
])
```

**Behavior:** Reads video file, performs object detection, and saves results.

### Example 2: Webcam with Real-time Processing
```python
Filter.run_multi([
    # ... other filters above
    (VideoIn, dict(
        sources='webcam://0',  # Default webcam
        outputs='tcp://*:5550',
        fps=30,
        sync=True,
    )),
    (FaceDetection, dict(
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

**Behavior:** Captures webcam feed, detects faces, and displays results in web browser.

### Example 3: IP Camera Monitoring
```python
Filter.run_multi([
    # ... other filters above
    (VideoIn, dict(
        sources='rtsp://admin:password@192.168.1.100:554/stream1',
        outputs='tcp://*:5550',
        sync=True,  # Important for network streams
        maxsize='1920x1080',
    )),
    (MotionDetection, dict(
        sources='tcp://localhost:5550',
        outputs='tcp://*:5552',
    )),
    (AlertSystem, dict(
        sources='tcp://localhost:5552',
        outputs='tcp://*:5554',
    )),
])
```

**Behavior:** Monitors IP camera for motion and sends alerts.

### Example 4: Multi-Camera Setup
```python
Filter.run_multi([
    # ... other filters above
    (VideoIn, dict(
        sources='webcam://0',  # Camera 1
        outputs='tcp://*:5550',
        fps=15,
    )),
    (VideoIn, dict(
        sources='webcam://1',  # Camera 2
        outputs='tcp://*:5552',
        fps=15,
    )),
    (VideoIn, dict(
        sources='rtsp://camera3.local/stream',
        outputs='tcp://*:5554',
        sync=True,
    )),
    (MultiCameraProcessor, dict(
        sources=['tcp://localhost:5550', 'tcp://localhost:5552', 'tcp://localhost:5554'],
        outputs='tcp://*:5556',
    )),
])
```

**Behavior:** Processes multiple camera feeds simultaneously.

### Example 5: Video Analysis with Looping
```python
Filter.run_multi([
    # ... other filters above
    (VideoIn, dict(
        sources='file:///short_video.mp4',
        outputs='tcp://*:5550',
        loop=True,  # Loop for continuous analysis
        resize='640x480',
    )),
    (Util, dict(
        sources='tcp://localhost:5550',
        outputs='tcp://*:5552',
        log=True,  # Log frame data
    )),
    (ObjectDetection, dict(
        sources='tcp://localhost:5552',
        outputs='tcp://*:5554',
    )),
    (Recorder, dict(
        sources='tcp://localhost:5554',
        outputs='file:///analysis/detections.jsonl',
        rules=['+main/data/detections'],
    )),
])
```

**Behavior:** Continuously analyzes video and records detection results.

### Example 6: S3 Video Processing
```python
Filter.run_multi([
    # ... other filters above
    (VideoIn, dict(
        sources='s3://my-video-bucket/sample.mp4',
        outputs='tcp://*:5550',
        loop=True,  # Loop for continuous processing
        maxsize='1280x720',
    )),
    (VideoProcessor, dict(
        sources='tcp://localhost:5550',
        outputs='tcp://*:5552',
    )),
    (VideoOut, dict(
        sources='tcp://localhost:5552',
        outputs='s3://processed-bucket/processed_sample.mp4',
    )),
])
```

**Behavior:** Processes video from S3 and saves results back to S3.

## Performance Considerations

### Video Processing Performance
- **Resolution Impact**: Higher resolution requires more processing power
- **Frame Rate**: Higher FPS increases processing load
- **Codec Complexity**: Different codecs have different decoding costs
- **Network Latency**: RTSP/HTTP streams add network overhead

### Memory Usage
- **Frame Buffering**: Video frames consume significant memory
- **Resize Operations**: Image resizing requires additional memory
- **Multiple Streams**: Each stream consumes memory independently
- **Looping**: Looping can accumulate memory over time

### Optimization Strategies
```python
# Optimize for performance
Filter.run_multi([
    # ... other filters above
    (VideoIn, dict(
        sources='file:///video.mp4',
        outputs='tcp://*:5550',
        resize='640x480',  # Smaller images
        fps=15,            # Lower frame rate
        sync=False,        # Disable sync for speed
    )),
])
```

## Error Handling

### Common Error Scenarios
- **File Not Found**: Video file doesn't exist
- **Invalid Format**: Unsupported video format
- **Camera Access**: Camera not available or in use
- **Network Issues**: RTSP/HTTP connection failures
- **Codec Issues**: Unsupported video codecs
- **Permission Errors**: File or camera access denied

### Error Recovery
- **Automatic Retry**: Retries failed connections
- **Graceful Degradation**: Continues with available sources
- **Error Logging**: Logs errors for debugging
- **Resource Cleanup**: Proper cleanup on failures

### Error Examples
```python
# File not found
sources='file:///nonexistent.mp4'  # Error: File not found

# Invalid camera index
sources='webcam://999'  # Error: Camera not available

# Invalid RTSP URL
sources='rtsp://invalid.url/stream'  # Error: Connection failed
```

## Debugging and Monitoring

### Debug Configuration
```python
import logging
logging.basicConfig(level=logging.DEBUG)

# Enable video input debugging
export DEBUG_VIDEO_IN=true
export LOG_LEVEL=DEBUG
```

### Debug Information
- **Source Status**: Shows source connection status
- **Frame Information**: Logs frame details and timing
- **Error Details**: Detailed error information
- **Performance Metrics**: Processing times and rates

### Monitoring
- **Frame Rates**: Track actual vs. target frame rates
- **Processing Times**: Monitor frame processing duration
- **Error Rates**: Track connection and processing errors
- **Resource Usage**: Monitor memory and CPU usage

## Troubleshooting

### Common Issues

#### Video File Issues
1. Check file format support
2. Verify file permissions
3. Ensure codec availability
4. Check file corruption

#### Camera Issues
1. Verify camera availability
2. Check camera permissions
3. Ensure camera not in use
4. Test camera with other software

#### Network Stream Issues
1. Check network connectivity
2. Verify RTSP/HTTP URLs
3. Check authentication credentials
4. Monitor network latency

#### Performance Issues
1. Reduce resolution and frame rate
2. Check system resources
3. Optimize processing pipeline
4. Consider hardware acceleration

### Debug Configuration
```python
# Enable comprehensive debugging
Filter.run_multi([
    # ... other filters above
    (VideoIn, dict(
        sources='file:///video.mp4',
        outputs='tcp://*:5550',
        sync=True,  # Enable sync for debugging
        fps=10,     # Lower FPS for monitoring
    )),
    (Util, dict(
        sources='tcp://localhost:5550',
        outputs='tcp://*:5552',
        log=True,   # Log frame data
    )),
])
```

## Advanced Usage

### Custom Video Processing
```python
# Custom video processing pipeline
Filter.run_multi([
    # ... other filters above
    (VideoIn, dict(
        sources='file:///video.mp4',
        outputs='tcp://*:5550',
        resize='1280x720',
        fps=30,
    )),
    (CustomProcessor, dict(
        sources='tcp://localhost:5550',
        outputs='tcp://*:5552',
    )),
])
```

### Multi-Format Support
```python
# Support multiple video formats
sources = [
    'file:///video1.mp4',
    'file:///video2.avi',
    'file:///video3.mov',
]

Filter.run_multi([
    # ... other filters above
    (VideoIn, dict(
        sources=sources,
        outputs='tcp://*:5550',
        loop=True,
    )),
])
```

### Dynamic Configuration
```python
# Dynamic configuration based on source type
def get_video_config(source):
    if source.startswith('rtsp://'):
        return {'sync': True, 'fps': 15}
    elif source.startswith('file://'):
        return {'loop': True, 'fps': 30}
    else:
        return {'fps': 30}

# Apply configuration
config = get_video_config('rtsp://camera.local/stream')
Filter.run_multi([
    # ... other filters above
    (VideoIn, dict(
        sources='rtsp://camera.local/stream',
        outputs='tcp://*:5550',
        **config
    )),
])
```

## API Reference

### VideoInConfig
```python
class VideoInConfig(FilterConfig):
    sources: str | list[str] | list[tuple[str, dict[str, Any]]]
    outputs: str | list[str] | list[tuple[str, dict[str, Any]]]
    bgr: bool | None
    sync: bool | None
    loop: bool | None
    fps: int | None
    maxsize: str | None
    resize: str | None
```

### VideoIn
```python
class VideoIn(Filter):
    FILTER_TYPE = 'Input'
    
    @classmethod
    def normalize_config(cls, config)
    def init(self, config)
    def setup(self, config)
    def shutdown(self)
    def process(self, frames)
    def read_video(self, source)
    def process_frame(self, frame, source_config)
    def apply_transforms(self, image, config)
    def resize_image(self, image, size)
    def convert_color(self, image, bgr)
```

### Environment Variables
- `DEBUG_VIDEO_IN`: Enable debug logging
- `FILTER_SOURCES`: Video input sources
- `FILTER_OUTPUTS`: Output destinations
- `FILTER_BGR`: Color format (BGR/RGB)
- `FILTER_SYNC`: Enable synchronization
- `FILTER_LOOP`: Enable video looping
- `FILTER_FPS`: Output frame rate
- `FILTER_MAXSIZE`: Maximum image size
- `FILTER_RESIZE`: Image resize dimensions
