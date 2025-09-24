# VideoOut Filter

The VideoOut filter is an output filter for OpenFilter that writes incoming Frame images to video files or RTSP streams. It supports segmented file output, adaptive FPS control, and various video encoding parameters. The filter uses the `vidgear` library for robust video writing and streaming capabilities.

## Overview

The VideoOut filter is designed to handle video output scenarios where you need to:
- Write processed images to video files in various formats
- Stream video to RTSP endpoints for live viewing
- Create segmented video files for organized storage
- Control video encoding parameters (quality, bitrate, codec)
- Handle adaptive frame rate based on input
- Support multiple output formats (MP4, AVI, MOV, etc.)
- Manage video file rotation and cleanup
- Stream to multiple RTSP clients simultaneously

## Key Features

- **Multiple Output Formats**: MP4, AVI, MOV, MKV, WebM
- **RTSP Streaming**: Live video streaming to RTSP endpoints
- **Segmented Output**: Automatic video file segmentation
- **Adaptive FPS**: Dynamic frame rate adjustment
- **Video Encoding**: Configurable codec and quality settings
- **File Management**: Automatic file rotation and cleanup
- **Multi-Stream Support**: Stream to multiple RTSP clients
- **Error Recovery**: Robust error handling and recovery

## Configuration

### Basic Configuration

```python
from openfilter.filter_runtime.filter import Filter
from openfilter.filter_runtime.filters.video_out import VideoOut

# Simple video file output
Filter.run_multi([
    (VideoOut, dict(
        sources='tcp://localhost:5550',
        outputs='file:///path/to/output.mp4',
    )),
])
```

### Advanced Configuration with Multiple Options

```python
# Video output with comprehensive options
Filter.run_multi([
    (VideoOut, dict(
        sources='tcp://localhost:5550',
        outputs='file:///path/to/output.mp4',
        fps=30,             # Output 30 FPS
        codec='libx264',    # H.264 codec
        bitrate='2M',       # 2 Mbps bitrate
        crf=23,             # Constant Rate Factor
        preset='medium',    # Encoding preset
        segment_duration=60, # 60-second segments
        max_files=10,       # Keep 10 files
    )),
])
```

### Environment Variables

You can configure via environment variables:

```bash
export FILTER_SOURCES="tcp://localhost:5550"
export FILTER_OUTPUTS="file:///path/to/output.mp4"
export FILTER_FPS="30"
export FILTER_CODEC="libx264"
export FILTER_BITRATE="2M"
export FILTER_CRF="23"
export FILTER_PRESET="medium"
export FILTER_SEGMENT_DURATION="60"
export FILTER_MAX_FILES="10"
```

## Output Destinations

### 1. Local Video Files

#### File Path Format
```python
outputs='file:///path/to/output.mp4'
outputs='file:///path/to/output.avi'
outputs='file:///path/to/output.mov'
```

#### Supported Formats
- **MP4**: H.264, H.265, MPEG-4
- **AVI**: Various codecs
- **MOV**: QuickTime format
- **MKV**: Matroska format
- **WebM**: WebM format

#### File Examples
```python
# Local file output
Filter.run_multi([
    (VideoOut, dict(
        sources='tcp://localhost:5550',
        outputs='file:///home/user/videos/output.mp4',
        fps=30,
    )),
])
```

### 2. RTSP Streaming

#### RTSP URL Format
```python
outputs='rtsp://server:port/stream'
outputs='rtsp://192.168.1.100:554/live'
```

#### RTSP Examples
```python
# RTSP streaming
Filter.run_multi([
    (VideoOut, dict(
        sources='tcp://localhost:5550',
        outputs='rtsp://192.168.1.100:554/live',
        fps=30,
        codec='libx264',
    )),
])
```

### 3. Segmented Output

#### Segment Configuration
```python
segment_duration=60  # 60-second segments
segment_duration=300 # 5-minute segments
segment_duration=None # No segmentation
```

#### Segment Examples
```python
# Segmented video output
Filter.run_multi([
    (VideoOut, dict(
        sources='tcp://localhost:5550',
        outputs='file:///videos/segment_{segment_number}.mp4',
        segment_duration=60,  # 60-second segments
        max_files=10,         # Keep 10 files
    )),
])
```

## Video Encoding Options

### Codec Selection (`codec`)

Controls the video codec used for encoding:

```python
codec='libx264'  # H.264 (default)
codec='libx265'  # H.265 (HEVC)
codec='libvpx'   # VP8
codec='libvpx-vp9' # VP9
```

#### Codec Examples
```python
# H.264 encoding
Filter.run_multi([
    (VideoOut, dict(
        sources='tcp://localhost:5550',
        outputs='file:///output.mp4',
        codec='libx264',
        crf=23,
    )),
])

# H.265 encoding for better compression
Filter.run_multi([
    (VideoOut, dict(
        sources='tcp://localhost:5550',
        outputs='file:///output.mp4',
        codec='libx265',
        crf=28,
    )),
])
```

### Quality Control

#### Constant Rate Factor (`crf`)
Controls video quality and file size:

```python
crf=18  # High quality, large file
crf=23  # Good quality, balanced (default)
crf=28  # Lower quality, smaller file
```

#### Bitrate Control (`bitrate`)
Controls target bitrate:

```python
bitrate='1M'   # 1 Mbps
bitrate='2M'   # 2 Mbps
bitrate='5M'   # 5 Mbps
```

#### Quality Examples
```python
# High quality output
Filter.run_multi([
    (VideoOut, dict(
        sources='tcp://localhost:5550',
        outputs='file:///high_quality.mp4',
        crf=18,
        preset='slow',  # Slower encoding for better quality
    )),
])

# Balanced quality and size
Filter.run_multi([
    (VideoOut, dict(
        sources='tcp://localhost:5550',
        outputs='file:///balanced.mp4',
        crf=23,
        preset='medium',
    )),
])

# Small file size
Filter.run_multi([
    (VideoOut, dict(
        sources='tcp://localhost:5550',
        outputs='file:///small.mp4',
        crf=28,
        bitrate='500k',
    )),
])
```

### Encoding Presets (`preset`)

Controls encoding speed vs. quality trade-off:

```python
preset='ultrafast'  # Fastest encoding, lower quality
preset='fast'       # Fast encoding
preset='medium'     # Balanced (default)
preset='slow'       # Slower encoding, better quality
preset='veryslow'   # Slowest encoding, best quality
```

#### Preset Examples
```python
# Fast encoding for real-time processing
Filter.run_multi([
    (VideoOut, dict(
        sources='tcp://localhost:5550',
        outputs='file:///fast.mp4',
        preset='fast',
        crf=25,
    )),
])

# High quality encoding
Filter.run_multi([
    (VideoOut, dict(
        sources='tcp://localhost:5550',
        outputs='file:///quality.mp4',
        preset='slow',
        crf=18,
    )),
])
```

## Frame Rate Control

### Output Frame Rate (`fps`)

Controls the output video frame rate:

```python
fps=30      # 30 FPS output
fps=60      # 60 FPS output
fps=15      # 15 FPS output
fps=None    # Adaptive FPS (default)
```

#### FPS Examples
```python
# Fixed 30 FPS output
Filter.run_multi([
    (VideoOut, dict(
        sources='tcp://localhost:5550',
        outputs='file:///output.mp4',
        fps=30,
    )),
])

# Adaptive FPS based on input
Filter.run_multi([
    (VideoOut, dict(
        sources='tcp://localhost:5550',
        outputs='file:///adaptive.mp4',
        fps=None,  # Adaptive FPS
    )),
])
```

### Adaptive FPS

When `fps=None`, the filter adapts to input frame rate:

```python
# Adaptive FPS examples
Filter.run_multi([
    (VideoOut, dict(
        sources='tcp://localhost:5550',
        outputs='file:///adaptive.mp4',
        fps=None,  # Will match input FPS
    )),
])
```

## File Management

### Segment Management

#### Segment Duration (`segment_duration`)
Controls how long each video segment should be:

```python
segment_duration=60   # 60-second segments
segment_duration=300  # 5-minute segments
segment_duration=3600 # 1-hour segments
segment_duration=None # No segmentation
```

#### Maximum Files (`max_files`)
Controls how many segment files to keep:

```python
max_files=10   # Keep 10 files
max_files=50   # Keep 50 files
max_files=None # Keep all files
```

#### Segment Examples
```python
# 1-minute segments, keep 10 files
Filter.run_multi([
    (VideoOut, dict(
        sources='tcp://localhost:5550',
        outputs='file:///segments/segment_{segment_number}.mp4',
        segment_duration=60,
        max_files=10,
    )),
])

# 5-minute segments, keep 20 files
Filter.run_multi([
    (VideoOut, dict(
        sources='tcp://localhost:5550',
        outputs='file:///segments/segment_{segment_number}.mp4',
        segment_duration=300,
        max_files=20,
    )),
])
```

### File Rotation

Automatic file rotation based on segments:

```python
# Automatic file rotation
Filter.run_multi([
    (VideoOut, dict(
        sources='tcp://localhost:5550',
        outputs='file:///videos/recording_{timestamp}.mp4',
        segment_duration=3600,  # 1-hour segments
        max_files=24,           # Keep 24 hours of recordings
    )),
])
```

## Usage Examples

### Example 1: Basic Video Recording
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
    (VideoOut, dict(
        sources='tcp://localhost:5552',
        outputs='file:///output/detected.mp4',
        fps=30,
    )),
])
```

**Behavior:** Records processed video with object detection results.

### Example 2: RTSP Live Streaming
```python
Filter.run_multi([
    (VideoIn, dict(
        sources='0',  # Webcam
        outputs='tcp://*:5550',
    )),
    (VideoOut, dict(
        sources='tcp://localhost:5550',
        outputs='rtsp://192.168.1.100:554/live',
        fps=30,
        codec='libx264',
        bitrate='2M',
    )),
])
```

**Behavior:** Streams webcam feed to RTSP endpoint.

### Example 3: Segmented Recording
```python
Filter.run_multi([
    (VideoIn, dict(
        sources='rtsp://camera.local/stream',
        outputs='tcp://*:5550',
    )),
    (VideoOut, dict(
        sources='tcp://localhost:5550',
        outputs='file:///recordings/segment_{segment_number}.mp4',
        segment_duration=300,  # 5-minute segments
        max_files=12,          # Keep 1 hour of recordings
        fps=15,
    )),
])
```

**Behavior:** Records camera stream in 5-minute segments, keeping 1 hour of recordings.

### Example 4: High Quality Recording
```python
Filter.run_multi([
    (VideoIn, dict(
        sources='file:///input.mp4',
        outputs='tcp://*:5550',
    )),
    (VideoProcessor, dict(
        sources='tcp://localhost:5550',
        outputs='tcp://*:5552',
    )),
    (VideoOut, dict(
        sources='tcp://localhost:5552',
        outputs='file:///high_quality.mp4',
        codec='libx265',  # H.265 for better compression
        crf=18,           # High quality
        preset='slow',    # Slow encoding for best quality
        fps=30,
    )),
])
```

**Behavior:** Creates high-quality H.265 encoded video.

### Example 5: Multi-Stream Output
```python
Filter.run_multi([
    (VideoIn, dict(
        sources='0',  # Webcam
        outputs='tcp://*:5550',
    )),
    (VideoOut, dict(
        sources='tcp://localhost:5550',
        outputs='file:///local_recording.mp4',
        fps=30,
    )),
    (VideoOut, dict(
        sources='tcp://localhost:5550',
        outputs='rtsp://192.168.1.100:554/live',
        fps=15,  # Lower FPS for streaming
        bitrate='1M',
    )),
])
```

**Behavior:** Records locally and streams simultaneously.

### Example 6: Surveillance System
```python
Filter.run_multi([
    (VideoIn, dict(
        sources='rtsp://camera.local/stream',
        outputs='tcp://*:5550',
    )),
    (MotionDetection, dict(
        sources='tcp://localhost:5550',
        outputs='tcp://*:5552',
    )),
    (VideoOut, dict(
        sources='tcp://localhost:5552',
        outputs='file:///surveillance/motion_{timestamp}.mp4',
        segment_duration=60,  # 1-minute segments
        max_files=1440,       # Keep 24 hours of recordings
        fps=15,
        codec='libx264',
        crf=25,
    )),
])
```

**Behavior:** Records motion-detected video in 1-minute segments for 24 hours.

## Performance Considerations

### Video Encoding Performance
- **Codec Choice**: H.264 is faster than H.265
- **Preset Selection**: Faster presets reduce CPU usage
- **Resolution Impact**: Higher resolution requires more processing
- **Frame Rate**: Higher FPS increases encoding load

### File I/O Performance
- **Disk Speed**: SSD vs. HDD affects write performance
- **Network Bandwidth**: RTSP streaming limited by network
- **File Size**: Larger files require more disk space
- **Segment Management**: Frequent segmentation can impact performance

### Memory Usage
- **Frame Buffering**: Video frames consume memory
- **Encoding Buffers**: Codec buffers add memory overhead
- **Multiple Streams**: Each stream consumes memory independently
- **Segment Management**: Segment metadata consumes memory

### Optimization Strategies
```python
# Optimize for performance
Filter.run_multi([
    (VideoOut, dict(
        sources='tcp://localhost:5550',
        outputs='file:///output.mp4',
        codec='libx264',  # Faster codec
        preset='fast',    # Faster preset
        crf=25,           # Balanced quality
        fps=15,           # Lower frame rate
    )),
])
```

## Error Handling

### Common Error Scenarios
- **Disk Space**: Insufficient disk space for recording
- **Permission Errors**: File write permission issues
- **Codec Issues**: Unsupported codec or parameters
- **Network Issues**: RTSP connection failures
- **File System**: File system errors or corruption
- **Memory Issues**: Insufficient memory for encoding

### Error Recovery
- **Automatic Retry**: Retries failed operations
- **Graceful Degradation**: Continues with available outputs
- **Error Logging**: Logs errors for debugging
- **Resource Cleanup**: Proper cleanup on failures

### Error Examples
```python
# Invalid codec
codec='invalid_codec'  # Error: Unsupported codec

# Invalid bitrate
bitrate='invalid'  # Error: Invalid bitrate format

# Permission denied
outputs='file:///root/output.mp4'  # Error: Permission denied
```

## Debugging and Monitoring

### Debug Configuration
```python
import logging
logging.basicConfig(level=logging.DEBUG)

# Enable video output debugging
export DEBUG_VIDEO_OUT=true
export LOG_LEVEL=DEBUG
```

### Debug Information
- **Output Status**: Shows output connection status
- **Encoding Information**: Logs encoding parameters and progress
- **File Operations**: Logs file write operations
- **Error Details**: Detailed error information

### Monitoring
- **Encoding Performance**: Track encoding speed and quality
- **File Sizes**: Monitor output file sizes
- **Error Rates**: Track encoding and file errors
- **Resource Usage**: Monitor CPU and memory usage

## Troubleshooting

### Common Issues

#### Encoding Problems
1. Check codec availability
2. Verify encoding parameters
3. Monitor system resources
4. Test with different presets

#### File Output Issues
1. Check disk space and permissions
2. Verify file path format
3. Monitor file system performance
4. Check for file locks

#### RTSP Streaming Issues
1. Verify network connectivity
2. Check RTSP server configuration
3. Monitor network bandwidth
4. Test with different clients

#### Performance Issues
1. Optimize encoding parameters
2. Check system resources
3. Consider hardware acceleration
4. Monitor disk I/O performance

### Debug Configuration
```python
# Enable comprehensive debugging
Filter.run_multi([
    (VideoOut, dict(
        sources='tcp://localhost:5550',
        outputs='file:///output.mp4',
        fps=15,      # Lower FPS for debugging
        crf=25,      # Balanced quality
        preset='fast', # Faster encoding
    )),
])
```

## Advanced Usage

### Custom Video Processing
```python
# Custom video processing with output
Filter.run_multi([
    (VideoIn, dict(
        sources='file:///input.mp4',
        outputs='tcp://*:5550',
    )),
    (CustomProcessor, dict(
        sources='tcp://localhost:5550',
        outputs='tcp://*:5552',
    )),
    (VideoOut, dict(
        sources='tcp://localhost:5552',
        outputs='file:///processed.mp4',
        codec='libx265',
        crf=20,
    )),
])
```

### Dynamic Configuration
```python
# Dynamic configuration based on input
def get_output_config(input_source):
    if 'camera' in input_source:
        return {'fps': 30, 'bitrate': '2M'}
    elif 'file' in input_source:
        return {'fps': None, 'crf': 23}
    else:
        return {'fps': 15, 'crf': 25}

# Apply configuration
config = get_output_config('camera')
Filter.run_multi([
    (VideoOut, dict(
        sources='tcp://localhost:5550',
        outputs='file:///output.mp4',
        **config
    )),
])
```

### Multi-Format Output
```python
# Output in multiple formats
Filter.run_multi([
    (VideoIn, dict(
        sources='file:///input.mp4',
        outputs='tcp://*:5550',
    )),
    (VideoOut, dict(
        sources='tcp://localhost:5550',
        outputs='file:///output_h264.mp4',
        codec='libx264',
        crf=23,
    )),
    (VideoOut, dict(
        sources='tcp://localhost:5550',
        outputs='file:///output_h265.mp4',
        codec='libx265',
        crf=28,
    )),
])
```

## API Reference

### VideoOutConfig
```python
class VideoOutConfig(FilterConfig):
    sources: str | list[str] | list[tuple[str, dict[str, Any]]]
    outputs: str | list[str] | list[tuple[str, dict[str, Any]]]
    fps: int | None
    codec: str | None
    bitrate: str | None
    crf: int | None
    preset: str | None
    segment_duration: int | None
    max_files: int | None
```

### VideoOut
```python
class VideoOut(Filter):
    FILTER_TYPE = 'Output'
    
    @classmethod
    def normalize_config(cls, config)
    def init(self, config)
    def setup(self, config)
    def shutdown(self)
    def process(self, frames)
    def write_video(self, frame, output_config)
    def create_encoder(self, config)
    def manage_segments(self, output_path)
    def cleanup_old_files(self, output_path, max_files)
```

### Environment Variables
- `DEBUG_VIDEO_OUT`: Enable debug logging
- `FILTER_SOURCES`: Input sources
- `FILTER_OUTPUTS`: Output destinations
- `FILTER_FPS`: Output frame rate
- `FILTER_CODEC`: Video codec
- `FILTER_BITRATE`: Target bitrate
- `FILTER_CRF`: Constant Rate Factor
- `FILTER_PRESET`: Encoding preset
- `FILTER_SEGMENT_DURATION`: Segment duration in seconds
- `FILTER_MAX_FILES`: Maximum number of files to keep
