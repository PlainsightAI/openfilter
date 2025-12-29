# Screen Capture Filter

The Screen Capture filter (ScreenIn) is an input filter for OpenFilter that captures the host computer's screen in real-time using VidGear's ScreenGear module. It supports multi-monitor capture, region selection, FPS control, and various platform-specific backends for optimal performance.

## Overview

The Screen Capture filter is designed to handle screen capture scenarios where you need to:
- Capture full screens from any connected monitor
- Capture specific regions of the screen
- Stream screen content to processing pipelines
- Monitor applications or desktop activity
- Record screen sessions
- Build remote desktop streaming solutions
- Create multi-monitor surveillance systems

## Key Features

- **Multi-Monitor Support**: Capture from any connected monitor simultaneously
- **Region Capture**: Capture specific rectangular areas instead of full screen
- **Real-time Streaming**: Live screen capture with minimal latency
- **FPS Control**: Configurable frame rate for performance optimization
- **Multiple Backends**: Platform-specific backends (mss, dxcam, pil) for optimal performance
- **Format Conversion**: BGR/RGB color space conversion
- **Image Resizing**: Dynamic image size adjustment
- **Cross-Platform**: Works on Windows, macOS, and Linux
- **Efficient Threading**: Background capture with latest-frame buffering

## Configuration

### Basic Configuration

```python
from openfilter.filter_runtime.filter import Filter
from openfilter.filter_runtime.filters.screen_in import ScreenIn

# Simple screen capture
Filter.run_multi([
    (ScreenIn, dict(
        sources='screen://0',
        outputs='tcp://*:5550',
    )),
])
```

### Advanced Configuration with Multiple Options

```python
# Screen capture with comprehensive options
Filter.run_multi([
    (ScreenIn, dict(
        sources='screen://0!maxfps=10!backend=mss',
        outputs='tcp://*:5550',
        bgr=True,              # BGR color format
        maxsize='1920x1080',   # Maximum size
        resize='800x600',      # Resize to specific dimensions
    )),
])
```

### Environment Variables

You can configure via environment variables:

```bash
export FILTER_SOURCES="screen://0"
export FILTER_OUTPUTS="tcp://*:5550"
export SCREEN_IN_BGR="true"
export SCREEN_IN_MAXFPS="10"
export SCREEN_IN_BACKEND="mss"
export SCREEN_IN_MAXSIZE="1920x1080"
```

## Input Sources

### 1. Monitor Selection

#### Monitor URL Format
```python
sources='screen://0'        # Primary monitor
sources='screen://1'        # Secondary monitor
sources='screen://2'        # Third monitor
sources='screen://-1'       # All monitors (backend specific)
```

#### Monitor Examples
```python
# Primary monitor
Filter.run_multi([
    (ScreenIn, dict(
        sources='screen://0',
        outputs='tcp://*:5550',
    )),
])

# Secondary monitor
Filter.run_multi([
    (ScreenIn, dict(
        sources='screen://1',
        outputs='tcp://*:5550',
    )),
])

# Multiple monitors with topics
Filter.run_multi([
    (ScreenIn, dict(
        sources='screen://0;monitor0, screen://1;monitor1',
        outputs='tcp://*:5550',
    )),
])
```

### 2. Region Capture

#### Region URL Format
```python
sources='screen://0?x=100&y=100&w=800&h=600'
sources='screen://0?x=0&y=0&width=1024&height=768'
```

#### Region Examples
```python
# Capture specific region
Filter.run_multi([
    (ScreenIn, dict(
        sources='screen://0?x=100&y=100&w=800&h=600',
        outputs='tcp://*:5550',
    )),
])

# Top-left quadrant
Filter.run_multi([
    (ScreenIn, dict(
        sources='screen://0?x=0&y=0&w=960&h=540',
        outputs='tcp://*:5550',
    )),
])
```

### 3. Backend Selection

#### Backend Options
- **mss**: Cross-platform, good performance (default)
- **dxcam**: Windows only, hardware accelerated (fastest on Windows)
- **pil**: Cross-platform, slower (fallback)

#### Backend Examples
```python
# Using mss (default)
Filter.run_multi([
    (ScreenIn, dict(
        sources='screen://0!backend=mss',
        outputs='tcp://*:5550',
    )),
])

# Using dxcam on Windows
Filter.run_multi([
    (ScreenIn, dict(
        sources='screen://0!backend=dxcam',
        outputs='tcp://*:5550',
    )),
])
```

## Configuration Options

### Monitor Selection (`monitor`)

Controls which monitor to capture:

```python
monitor=0   # Primary monitor (default)
monitor=1   # Secondary monitor
monitor=-1  # All monitors (backend specific)
```

#### Monitor Selection Examples
```python
# Explicit monitor selection
Filter.run_multi([
    (ScreenIn, dict(
        sources='screen://0!monitor=0',  # Primary
        outputs='tcp://*:5550',
    )),
])
```

### Region Parameters

Controls the captured region:

```python
x=100        # X coordinate of top-left corner
y=100        # Y coordinate of top-left corner
width=800    # Region width in pixels
height=600   # Region height in pixels
```

#### Region Parameter Examples
```python
# Using query parameters
Filter.run_multi([
    (ScreenIn, dict(
        sources='screen://0?x=100&y=100&w=800&h=600',
        outputs='tcp://*:5550',
    )),
])

# Using inline options
Filter.run_multi([
    (ScreenIn, dict(
        sources='screen://0!x=100!y=100!width=800!height=600',
        outputs='tcp://*:5550',
    )),
])
```

### Frame Rate Control (`maxfps`)

Controls output frame rate:

```python
maxfps=5      # 5 FPS (low CPU usage)
maxfps=15     # 15 FPS (balanced)
maxfps=30     # 30 FPS (smooth capture)
maxfps=None   # Uncapped (default)
```

#### FPS Control Examples
```python
# Low FPS for monitoring
Filter.run_multi([
    (ScreenIn, dict(
        sources='screen://0!maxfps=5',
        outputs='tcp://*:5550',
    )),
])

# Smooth capture
Filter.run_multi([
    (ScreenIn, dict(
        sources='screen://0!maxfps=30',
        outputs='tcp://*:5550',
    )),
])
```

### Color Format (`bgr`)

Controls the color format of output images:

```python
bgr=True   # BGR format (default for OpenCV)
bgr=False  # RGB format (for ML frameworks)
```

#### Color Format Examples
```python
# BGR format for OpenCV processing
Filter.run_multi([
    (ScreenIn, dict(
        sources='screen://0',
        outputs='tcp://*:5550',
        bgr=True,
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
    (ScreenIn, dict(
        sources='screen://0!resize=1280x720',
        outputs='tcp://*:5550',
    )),
])

# Maximum size limit
Filter.run_multi([
    (ScreenIn, dict(
        sources='screen://0!maxsize=1920x1080',
        outputs='tcp://*:5550',
    )),
])
```

### Backend Selection (`backend`)

Controls the ScreenGear backend:

```python
backend='mss'     # Cross-platform (default)
backend='dxcam'   # Windows only (fastest)
backend='pil'     # Cross-platform (slowest)
```

#### Backend Examples
```python
# Windows optimization
Filter.run_multi([
    (ScreenIn, dict(
        sources='screen://0!backend=dxcam!maxfps=30',
        outputs='tcp://*:5550',
    )),
])
```

## Usage Examples

### Example 1: Basic Screen Capture
```python
Filter.run_multi([
    (ScreenIn, dict(
        sources='screen://0',
        outputs='tcp://*:5550',
    )),
    (Webvis, dict(
        sources='tcp://localhost:5550',
        port=8000,
    )),
])
```

**Behavior:** Captures primary monitor and displays in web browser.

### Example 2: Screen Recording
```python
Filter.run_multi([
    (ScreenIn, dict(
        sources='screen://0!maxfps=30',
        outputs='tcp://*:5550',
    )),
    (VideoOut, dict(
        sources='tcp://localhost:5550',
        outputs='file:///recordings/screen_{timestamp}.mp4',
    )),
])
```

**Behavior:** Records screen to MP4 file at 30 FPS.

### Example 3: Multi-Monitor Surveillance
```python
Filter.run_multi([
    (ScreenIn, dict(
        sources='screen://0;monitor0!maxfps=10, screen://1;monitor1!maxfps=10',
        outputs='tcp://*:5550',
    )),
    (Webvis, dict(
        sources='tcp://localhost:5550',
        port=8000,
    )),
])
```

**Behavior:** Captures two monitors simultaneously, accessible at `/monitor0` and `/monitor1`.

### Example 4: Region Monitoring
```python
Filter.run_multi([
    (ScreenIn, dict(
        sources='screen://0?x=100&y=100&w=800&h=600!maxfps=15',
        outputs='tcp://*:5550',
    )),
    (Webvis, dict(
        sources='tcp://localhost:5550',
        port=8000,
    )),
])
```

**Behavior:** Monitors specific region of screen at 15 FPS.

### Example 5: Optimized Performance Capture
```python
Filter.run_multi([
    (ScreenIn, dict(
        sources='screen://0!maxfps=5!resize=1280x720!backend=mss',
        outputs='tcp://*:5550',
    )),
    (Webvis, dict(
        sources='tcp://localhost:5550',
        port=8000,
    )),
])
```

**Behavior:** Low CPU usage capture with 5 FPS and 720p resolution.

### Example 6: Screen Analysis Pipeline
```python
Filter.run_multi([
    (ScreenIn, dict(
        sources='screen://0!maxfps=10',
        outputs='tcp://*:5550',
    )),
    (Util, dict(
        sources='tcp://localhost:5550',
        outputs='tcp://*:5552',
        xforms='resize 800x600',
    )),
    (ObjectDetection, dict(
        sources='tcp://localhost:5552',
        outputs='tcp://*:5554',
    )),
    (Webvis, dict(
        sources='tcp://localhost:5554',
        port=8000,
    )),
])
```

**Behavior:** Captures screen, resizes, detects objects, and displays results.

### Example 7: Remote Desktop Streaming
```python
Filter.run_multi([
    (ScreenIn, dict(
        sources='screen://0!maxfps=15!resize=1280x720',
        outputs='tcp://*:5550',
    )),
    (VideoOut, dict(
        sources='tcp://localhost:5550',
        outputs='rtmp://streaming-server/live/desktop',
    )),
])
```

**Behavior:** Streams desktop to RTMP server for remote viewing.

### Example 8: Application Window Monitoring
```python
Filter.run_multi([
    (ScreenIn, dict(
        sources='screen://0?x=200&y=100&w=1024&h=768!maxfps=10',
        outputs='tcp://*:5550',
    )),
    (Util, dict(
        sources='tcp://localhost:5550',
        outputs='tcp://*:5552',
        log=True,  # Log frame metadata
    )),
    (Recorder, dict(
        sources='tcp://localhost:5552',
        outputs='file:///logs/app_activity.jsonl',
    )),
])
```

**Behavior:** Monitors application window and logs activity to file.

## Performance Considerations

### Screen Capture Performance
- **Resolution Impact**: Higher resolution requires more processing power
- **Frame Rate**: Higher FPS increases CPU and memory usage
- **Backend Choice**: dxcam (Windows) offers hardware acceleration
- **Region Capture**: Smaller regions reduce capture overhead

### Memory Usage
- **Frame Buffering**: Only latest frame is stored in memory
- **Resize Operations**: Image resizing requires additional memory
- **Multiple Monitors**: Each monitor consumes memory independently

### Optimization Strategies
```python
# Optimize for low CPU usage
Filter.run_multi([
    (ScreenIn, dict(
        sources='screen://0!maxfps=5!resize=800x600!backend=mss',
        outputs='tcp://*:5550',
    )),
])

# Optimize for quality
Filter.run_multi([
    (ScreenIn, dict(
        sources='screen://0!maxfps=30!backend=dxcam',  # Windows only
        outputs='tcp://*:5550',
    )),
])

# Optimize for specific region
Filter.run_multi([
    (ScreenIn, dict(
        sources='screen://0?x=0&y=0&w=800&h=600!maxfps=15',
        outputs='tcp://*:5550',
    )),
])
```

## Error Handling

### Common Error Scenarios
- **Invalid Monitor Index**: Monitor number doesn't exist
- **Permission Denied**: Screen recording permission not granted (macOS)
- **Backend Not Available**: Requested backend not installed
- **Region Out of Bounds**: Region coordinates exceed screen size
- **ScreenGear Initialization**: Backend fails to initialize

### Error Recovery
- **Automatic Retry**: Attempts to reinitialize on transient failures
- **Graceful Degradation**: Falls back to default backend if specified backend fails
- **Error Logging**: Logs detailed error information for debugging
- **Resource Cleanup**: Proper cleanup on failures

### Error Examples
```python
# Invalid monitor index
sources='screen://999'  # Error: Monitor not found

# Permission denied (macOS)
sources='screen://0'  # Error: Screen recording permission required

# Backend not available
sources='screen://0!backend=dxcam'  # Error: dxcam not installed (non-Windows)
```

## Platform-Specific Considerations

### Windows

**Recommended Backend**: `dxcam` (hardware accelerated)

**Installation:**
```bash
pip install dxcam
```

**Configuration:**
```python
(ScreenIn, dict(
    sources='screen://0!backend=dxcam!maxfps=30',
    outputs='tcp://*:5550',
))
```

**Performance:**
- dxcam offers best performance via DirectX hardware acceleration
- Falls back to mss if dxcam not available
- No special permissions required

### macOS

**Recommended Backend**: `mss`

**Permissions Required:**
1. Open **System Preferences** → **Security & Privacy** → **Privacy** → **Screen Recording**
2. Add Python or your terminal app to allowed applications
3. Restart terminal/IDE after granting permission

**Configuration:**
```python
(ScreenIn, dict(
    sources='screen://0!backend=mss!maxfps=15',
    outputs='tcp://*:5550',
))
```

**Performance:**
- mss provides good performance on macOS
- Screen recording permission is mandatory
- First run may require permission prompt

### Linux

**Recommended Backend**: `mss`

**Requirements:**
- X11 display server (Wayland may require special handling)
- mss package installed

**Installation:**
```bash
pip install mss
```

**Configuration:**
```python
(ScreenIn, dict(
    sources='screen://0!backend=mss!maxfps=15',
    outputs='tcp://*:5550',
))
```

**Performance:**
- mss works reliably on X11
- Performance varies by distribution and display server
- No special permissions typically required

## Debugging and Monitoring

### Debug Configuration
```python
import logging
logging.basicConfig(level=logging.DEBUG)

# Enable screen capture debugging
export DEBUG_SCREEN_IN=true
export LOG_LEVEL=DEBUG
```

### Debug Information
- **Source Status**: Shows screen capture connection status
- **Frame Information**: Logs frame details and timing
- **Backend Status**: Shows which backend is active
- **Performance Metrics**: Processing times and frame rates

### Monitoring
- **Frame Rates**: Track actual vs. target frame rates
- **Processing Times**: Monitor frame capture duration
- **Error Rates**: Track capture failures
- **Resource Usage**: Monitor memory and CPU usage

## Troubleshooting

### Common Issues

#### Permission Denied (macOS)
**Symptoms:** Screen capture fails immediately

**Solution:**
1. Open System Preferences → Security & Privacy → Privacy → Screen Recording
2. Add Python or terminal to allowed apps
3. Restart terminal/IDE

#### Backend Not Found
**Symptoms:** `ModuleNotFoundError: No module named 'mss'`

**Solution:**
```bash
pip install mss
```

#### Poor Performance
**Symptoms:** High CPU usage or low frame rate

**Solutions:**
1. Lower FPS: `maxfps=5` instead of `maxfps=30`
2. Resize capture: `resize=1280x720`
3. Use region capture: `screen://0?x=0&y=0&w=800&h=600`
4. Windows: Use dxcam backend for hardware acceleration

#### Invalid Monitor Index
**Symptoms:** `Invalid monitor index` error

**Solution:**
- Use `monitor=0` for primary monitor
- Verify monitor exists before using index > 0
- Use `mss.mss().monitors` to list available monitors

#### Black Screen Capture
**Symptoms:** Captured frames are all black

**Solutions:**
1. Check screen recording permissions (macOS)
2. Verify monitor is powered on and displaying content
3. Try different backend: `backend=pil` or `backend=mss`
4. Check if application requires elevated permissions

## Advanced Usage

### Custom Processing Pipeline
```python
Filter.run_multi([
    (ScreenIn, dict(
        sources='screen://0?x=100&y=100&w=1024&h=768!maxfps=15',
        outputs='tcp://*:5550',
    )),
    (Util, dict(
        sources='tcp://localhost:5550',
        outputs='tcp://*:5552',
        xforms='resize 800x600, box 0.1+0.1x0.2x0.05#ff0000',
    )),
    (Webvis, dict(
        sources='tcp://localhost:5552',
        port=8000,
    )),
])
```

### Multi-Monitor with Different Settings
```python
Filter.run_multi([
    (ScreenIn, dict(
        sources='screen://0!maxfps=30!backend=dxcam;high_fps, screen://1!maxfps=10!resize=800x600;low_fps',
        outputs='tcp://*:5550',
    )),
    (Webvis, dict(
        sources='tcp://localhost:5550',
        port=8000,
    )),
])
```

### Environment Variable Configuration
```bash
# Set global defaults
export SCREEN_IN_MAXFPS=10
export SCREEN_IN_BACKEND=mss
export SCREEN_IN_BGR=true
export SCREEN_IN_RESIZE=1280x720

# Run filter
python my_screen_capture.py
```

## API Reference

### ScreenInConfig
```python
class ScreenInConfig(FilterConfig):
    sources: str | list[str] | list[Source]
    outputs: str | list[str]
    bgr: bool | None
    maxfps: float | None
    maxsize: str | None
    resize: str | None
    backend: str | None
```

### ScreenIn
```python
class ScreenIn(Filter):
    FILTER_TYPE = 'Input'

    @classmethod
    def normalize_config(cls, config)
    def init(self, config)
    def setup(self, config)
    def shutdown(self)
    def process(self, frames)
```

### Environment Variables
- `SCREEN_IN_BGR`: Default color format (true/false)
- `SCREEN_IN_MAXFPS`: Default maximum FPS
- `SCREEN_IN_BACKEND`: Default backend (mss/dxcam/pil)
- `SCREEN_IN_MAXSIZE`: Default maximum size
- `SCREEN_IN_RESIZE`: Default resize dimensions
- `FILTER_SOURCES`: Screen sources
- `FILTER_OUTPUTS`: Output destinations

## Best Practices

### Performance Optimization
1. Use appropriate FPS for your use case (5-10 FPS for monitoring, 30 FPS for recording)
2. Resize to lower resolution when possible
3. Use region capture for application-specific monitoring
4. Choose optimal backend for your platform (dxcam on Windows, mss elsewhere)

### Resource Management
1. Stop capture when not needed to free resources
2. Use single filter instance for multiple topics instead of multiple filters
3. Monitor CPU and memory usage during long-running captures

### Error Handling
1. Check monitor availability before capturing
2. Handle permission errors gracefully
3. Implement retry logic for transient failures
4. Log errors for debugging

### Security Considerations
1. Be aware that screen capture may record sensitive information
2. Ensure proper permissions on recording files
3. Comply with privacy regulations when recording user sessions
4. Inform users when screen recording is active
