# VideoOut Filter

The VideoOut filter is an output filter for OpenFilter that writes incoming Frame images to video files or RTSP streams. It supports segmented file output by time, adaptive FPS control, and various video encoding parameters through the `params` dictionary. The filter uses the `vidgear` library for robust video writing and streaming capabilities.

> Note: THIS IS NOT A RTSP SERVER. Keep in mind that when using RTSP stream as an output you will still need to use a RTSP server such as `mediamtx`.

## Overview

The VideoOut filter is designed to handle video output scenarios where you need to:
- Write processed images to video files in various formats
- Stream video to RTSP endpoints for live viewing
- Create segmented video files based on time duration
- Control video encoding parameters via the `params` dictionary
- Handle adaptive frame rate based on input
- Support multiple output formats (MP4, AVI, MOV, etc.)
- Stream to multiple RTSP clients simultaneously

## Key Features

- **Multiple Output Formats**: MP4, AVI, MOV, MKV, WebM
- **RTSP Streaming**: Live video streaming to RTSP endpoints
- **Time-based Segmentation**: Automatic video file segmentation by time (in minutes)
- **Adaptive FPS**: Dynamic frame rate adjustment based on input
- **Video Encoding**: Configurable encoding parameters via `params` dictionary
- **Multi-Stream Support**: Stream to multiple RTSP clients
- **Error Recovery**: Robust error handling and recovery

## Configuration

### Basic Configuration

```python
from openfilter.filter_runtime.filter import Filter
from openfilter.filter_runtime.filters.video_out import VideoOut

# Simple video file output
Filter.run_multi([
    # ... other filters above
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
    # ... other filters above
    (VideoOut, dict(
        sources='tcp://localhost:5550',
        outputs='file:///path/to/output.mp4!segtime=1',  # 1-minute segments
        fps=30,             # Output 30 FPS
        params={
            'crf': 23,           # Constant Rate Factor (quality)
            'preset': 'medium',  # Encoding preset
            'bitrate': '2M',     # 2 Mbps bitrate
        }
    )),
])
```

### Environment Variables

You can configure via environment variables:

```bash
export VIDEO_OUT_BGR="true"           # BGR format (default: true)
export VIDEO_OUT_FPS="30"             # Default FPS (default: 15)
export VIDEO_OUT_SEGTIME="1"          # Default segment time in minutes
export VIDEO_OUT_PARAMS='{"crf": 23}' # Default encoding parameters
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
    # ... other filters above
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
    # ... other filters above
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
# Using segtime in output string (in minutes)
outputs='file:///output.mp4!segtime=1'    # 1-minute segments
outputs='file:///output.mp4!segtime=5'    # 5-minute segments
outputs='file:///output.mp4'              # No segmentation

# Or using segtime parameter
segtime=1    # 1-minute segments
segtime=5    # 5-minute segments  
segtime=None # No segmentation
```

#### Segment Examples
```python
# Segmented video output
Filter.run_multi([
    # ... other filters above
    (VideoOut, dict(
        sources='tcp://localhost:5550',
        outputs='file:///videos/recording_%Y%m%d_%H%M%S.mp4!segtime=1',  # 1-minute segments
        fps=30,
    )),
])
```

## Video Encoding Options

### Encoding Parameters (`params`)

All video encoding parameters are controlled through the `params` dictionary:

```python
params={
    'crf': 23,           # Constant Rate Factor (0=best quality, 51=worst)
    'preset': 'medium',  # Encoding preset (ultrafast, fast, medium, slow, veryslow)
    'bitrate': '2M',     # Target bitrate
    'pix_fmt': 'yuv420p', # Pixel format
    'g': 50,             # Group of pictures (GOP) size
    'vf': 'scale=1280:720' # Video filters
}
```

#### Codec Examples
```python
# H.264 encoding
Filter.run_multi([
    # ... other filters above
    (VideoOut, dict(
        sources='tcp://localhost:5550',
        outputs='file:///output.mp4',
        params={'crf': 23, 'preset': 'medium'},
    )),
])

# H.265 encoding for better compression
Filter.run_multi([
    # ... other filters above
    (VideoOut, dict(
        sources='tcp://localhost:5550',
        outputs='file:///output.mp4',
        params={'crf': 28, 'preset': 'slow'},
    )),
])
```

### Quality Control

#### Constant Rate Factor (`crf`)
Controls video quality and file size:

```python
params={'crf': 18}  # High quality, large file
params={'crf': 23}  # Good quality, balanced
params={'crf': 28}  # Lower quality, smaller file
```

#### Bitrate Control (`bitrate`)
Controls target bitrate:

```python
params={'bitrate': '1M'}   # 1 Mbps
params={'bitrate': '2M'}   # 2 Mbps
params={'bitrate': '5M'}   # 5 Mbps
```

#### Quality Examples
```python
# High quality output
Filter.run_multi([
    # ... other filters above
    (VideoOut, dict(
        sources='tcp://localhost:5550',
        outputs='file:///high_quality.mp4',
        params={'crf': 18, 'preset': 'slow'},  # Slower encoding for better quality
    )),
])

# Balanced quality and size
Filter.run_multi([
    # ... other filters above
    (VideoOut, dict(
        sources='tcp://localhost:5550',
        outputs='file:///balanced.mp4',
        params={'crf': 23, 'preset': 'medium'},
    )),
])

# Small file size
Filter.run_multi([
    # ... other filters above
    (VideoOut, dict(
        sources='tcp://localhost:5550',
        outputs='file:///small.mp4',
        params={'crf': 28, 'bitrate': '500k'},
    )),
])
```

### Encoding Presets (`preset`)

Controls encoding speed vs. quality trade-off:

```python
params={'preset': 'ultrafast'}  # Fastest encoding, lower quality
params={'preset': 'fast'}       # Fast encoding
params={'preset': 'medium'}     # Balanced (default)
params={'preset': 'slow'}       # Slower encoding, better quality
params={'preset': 'veryslow'}   # Slowest encoding, best quality
```

#### Preset Examples
```python
# Fast encoding for real-time processing
Filter.run_multi([
    # ... other filters above
    (VideoOut, dict(
        sources='tcp://localhost:5550',
        outputs='file:///fast.mp4',
        params={'preset': 'fast', 'crf': 25},
    )),
])

# High quality encoding
Filter.run_multi([
    # ... other filters above
    (VideoOut, dict(
        sources='tcp://localhost:5550',
        outputs='file:///quality.mp4',
        params={'preset': 'slow', 'crf': 18},
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
fps=True    # Adaptive FPS (recommended)
fps=None    # Uses environment variable default (15)
```

#### FPS Examples
```python
# Fixed 30 FPS output
Filter.run_multi([
    # ... other filters above
    (VideoOut, dict(
        sources='tcp://localhost:5550',
        outputs='file:///output.mp4',
        fps=30,
    )),
])

# Adaptive FPS based on input (recommended)
Filter.run_multi([
    # ... other filters above
    (VideoOut, dict(
        sources='tcp://localhost:5550',
        outputs='file:///adaptive.mp4',
        fps=True,  # Adaptive FPS
    )),
])
```

### Adaptive FPS

When `fps=True`, the filter adapts to input frame rate by tracking the rate at which frames are written and setting this rate for each new file segment or restarting the RTSP stream if the rate strays too far from what the stream is set to.

```python
# Adaptive FPS examples
Filter.run_multi([
    # ... other filters above
    (VideoOut, dict(
        sources='tcp://localhost:5550',
        outputs='file:///adaptive.mp4!segtime=1',  # Requires segmentation for adaptive FPS
        fps=True,  # Will match input FPS
    )),
])
```

**Note:** Adaptive FPS only works for files if they are output in segments (`segtime` specified), otherwise there will never be an opportunity to set a more correct framerate than the initial guess.

## File Management

### Segment Management

#### Segment Duration (`segtime`)
Controls how long each video segment should be (in **minutes**):

```python
segtime=1      # 1-minute segments
segtime=5      # 5-minute segments
segtime=60     # 1-hour segments
segtime=None   # No segmentation
```

#### Segment Examples
```python
# 1-minute segments
Filter.run_multi([
    # ... other filters above
    (VideoOut, dict(
        sources='tcp://localhost:5550',
        outputs='file:///segments/recording_%Y%m%d_%H%M%S.mp4!segtime=1',
        fps=30,
    )),
])

# 5-minute segments
Filter.run_multi([
    # ... other filters above
    (VideoOut, dict(
        sources='tcp://localhost:5550',
        outputs='file:///segments/recording_%Y%m%d_%H%M%S.mp4!segtime=5',
        fps=30,
    )),
])
```

**Note:** The VideoOut filter does **not** provide automatic file rotation or `max_files` functionality. You would need to implement this separately if needed.

### File Rotation

The VideoOut filter creates new files based on the `segtime` parameter and filename templating:

```python
# Automatic file rotation with timestamped filenames
Filter.run_multi([
    # ... other filters above
    (VideoOut, dict(
        sources='tcp://localhost:5550',
        outputs='file:///videos/recording_%Y%m%d_%H%M%S.mp4!segtime=60',  # 1-hour segments
        fps=30,
    )),
])
```

**Filename templating:** You can use `strftime` formatting in the output filename. The filter will also append a segment index (e.g., `_000001`, `_000002`) to distinguish segments.

## Usage Examples

### Example 1: Basic Video Recording
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
    # ... other filters above
    (VideoIn, dict(
        sources='0',  # Webcam
        outputs='tcp://*:5550',
    )),
    (VideoOut, dict(
        sources='tcp://localhost:5550',
        outputs='rtsp://192.168.1.100:554/live',
        fps=30,
        params={'bitrate': '2M'},
    )),
])
```

**Behavior:** Streams webcam feed to RTSP endpoint.

### Example 3: Segmented Recording
```python
Filter.run_multi([
    # ... other filters above
    (VideoIn, dict(
        sources='rtsp://camera.local/stream',
        outputs='tcp://*:5550',
    )),
    (VideoOut, dict(
        sources='tcp://localhost:5550',
        outputs='file:///recordings/recording_%Y%m%d_%H%M%S.mp4!segtime=5',  # 5-minute segments
        fps=15,
    )),
])
```

**Behavior:** Records camera stream in 5-minute segments with timestamped filenames.

### Example 4: High Quality Recording
```python
Filter.run_multi([
    # ... other filters above
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
        fps=30,
        params={
            'crf': 18,        # High quality
            'preset': 'slow', # Slow encoding for best quality
        }
    )),
])
```

**Behavior:** Creates high-quality encoded video with slow preset for best quality.

### Example 5: Multi-Stream Output
```python
Filter.run_multi([
    # ... other filters above
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
        params={'bitrate': '1M'},
    )),
])
```

**Behavior:** Records locally and streams simultaneously.

### Example 6: Surveillance System
```python
Filter.run_multi([
    # ... other filters above
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
        outputs='file:///surveillance/motion_%Y%m%d_%H%M%S.mp4!segtime=1',  # 1-minute segments
        fps=15,
        params={'crf': 25},
    )),
])
```

**Behavior:** Records motion-detected video in 1-minute segments with timestamped filenames.

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
    # ... other filters above
    (VideoOut, dict(
        sources='tcp://localhost:5550',
        outputs='file:///output.mp4',
        fps=15,           # Lower frame rate
        params={
            'preset': 'fast',    # Faster preset
            'crf': 25,           # Balanced quality
        }
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
# Invalid parameters
params={'invalid_param': 'value'}  # Error: Unknown parameter

# Invalid bitrate format
params={'bitrate': 'invalid'}  # Error: Invalid bitrate format

# Permission denied
outputs='file:///root/output.mp4'  # Error: Permission denied
```

## Debugging and Monitoring

### Debug Configuration
```python
import logging
logging.basicConfig(level=logging.DEBUG)

# Enable video output debugging
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
    # ... other filters above
    (VideoOut, dict(
        sources='tcp://localhost:5550',
        outputs='file:///output.mp4',
        fps=15,      # Lower FPS for debugging
        params={
            'crf': 25,      # Balanced quality
            'preset': 'fast', # Faster encoding
        }
    )),
])
```

## Advanced Usage

### Custom Video Processing
```python
# Custom video processing with output
Filter.run_multi([
    # ... other filters above
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
        params={'crf': 20},
    )),
])
```

### Dynamic Configuration
```python
# Dynamic configuration based on input
def get_output_config(input_source):
    if 'camera' in input_source:
        return {'fps': 30, 'params': {'bitrate': '2M'}}
    elif 'file' in input_source:
        return {'fps': True, 'params': {'crf': 23}}
    else:
        return {'fps': 15, 'params': {'crf': 25}}

# Apply configuration
config = get_output_config('camera')
Filter.run_multi([
    # ... other filters above
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
    # ... other filters above
    (VideoIn, dict(
        sources='file:///input.mp4',
        outputs='tcp://*:5550',
    )),
    (VideoOut, dict(
        sources='tcp://localhost:5550',
        outputs='file:///output_h264.mp4',
        params={'crf': 23},
    )),
    (VideoOut, dict(
        sources='tcp://localhost:5550',
        outputs='file:///output_h265.mp4',
        params={'crf': 28},
    )),
])
```

## API Reference

### VideoOutConfig
```python
class VideoOutConfig(FilterConfig):
    sources: str | list[str]
    outputs: str | list[str | Output]
    bgr: bool | None                    # BGR vs RGB format
    fps: float | Literal[True] | None   # Frame rate (True = adaptive)
    segtime: float | None               # Segment time in minutes
    params: dict[str, Any] | None       # Video encoding parameters
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
    def process_src_fps(self, frames)    # For adaptive FPS
    def process_check_rtsp_fps(self, frames)
```

### Environment Variables
- `VIDEO_OUT_BGR`: BGR format (default: true)
- `VIDEO_OUT_FPS`: Default FPS (default: 15)
- `VIDEO_OUT_SEGTIME`: Default segment time in minutes
- `VIDEO_OUT_PARAMS`: Default encoding parameters as JSON string
