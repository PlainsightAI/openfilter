# ScreenIn Filter Examples

This directory contains examples demonstrating the **ScreenIn** filter for OpenFilter. The ScreenIn filter captures the host computer's screen in real-time using VidGear's ScreenGear module, enabling live screen monitoring, recording, and processing pipelines.

## Overview

The ScreenIn filter supports:
- **Multi-monitor capture**: Capture from any connected monitor
- **Region capture**: Capture specific areas of the screen
- **FPS control**: Adjust frame rate for performance optimization
- **Multiple backends**: Platform-specific optimization (mss, dxcam, pil)
- **Real-time streaming**: Live screen capture to downstream filters

## Installation

### Prerequisites

```bash
# Install OpenFilter (if not already installed)
pip install openfilter

# Install required dependencies
pip install -r requirements.txt
```

### Platform-Specific Setup

#### macOS
Screen recording permission is required:
1. Go to **System Preferences** → **Security & Privacy** → **Privacy** → **Screen Recording**
2. Add Python or your terminal app to the allowed applications
3. Restart your terminal/IDE

#### Windows
For best performance, install dxcam (hardware accelerated):
```bash
pip install dxcam
```

#### Linux
Requires X11 display server. mss should work out of the box:
```bash
pip install mss
```

## Examples

### Basic Example: `main.py`

The simplest example - captures the primary monitor at 10 FPS and displays in browser.

**Run:**
```bash
python main.py
```

**What it does:**
- Captures monitor 0 (primary) at 10 FPS
- Streams to Webvis for browser display
- Opens at http://localhost:8000

**Code:**
```python
Filter.run_multi([
    (ScreenIn, dict(
        sources='screen://0!maxfps=10',
        outputs='tcp://*:5550',
    )),
    (Webvis, dict(
        sources='tcp://127.0.0.1:5550',
        host='127.0.0.1',
        port=8000,
    )),
])
```

### Scenario 1: Region Capture

Demonstrates capturing a specific region instead of the full screen.

**Run:**
```bash
python scenario1_region_capture.py
```

**What it does:**
- Captures 800x600 region starting at (100, 100)
- Useful for monitoring specific applications
- 15 FPS capture rate

**Configuration:**
```python
sources='screen://0?x=100&y=100&w=800&h=600!maxfps=15'
```

**Use cases:**
- Application-specific monitoring
- Reducing capture area for performance
- Focused screen recording

### Scenario 2: Multi-Monitor Capture

Demonstrates capturing from multiple monitors simultaneously.

**Run:**
```bash
python scenario2_multi_monitor.py
```

**Requirements:**
- At least 2 monitors connected to your system
- If only 1 monitor available, second source will fail gracefully

**What it does:**
- Captures monitor 0 → topic 'monitor0'
- Captures monitor 1 → topic 'monitor1'
- Each accessible at different URLs

**Access:**
- Monitor 0: http://localhost:8000/monitor0
- Monitor 1: http://localhost:8000/monitor1

**Configuration:**
```python
sources='screen://0!maxfps=10;monitor0, screen://1!maxfps=10;monitor1'
```

**Use cases:**
- Multi-monitor surveillance
- Comparing displays
- Independent monitor processing

### Scenario 3: FPS Control

Demonstrates controlling frame rate for performance optimization.

**Run:**
```bash
python scenario3_fps_control.py
```

**What it does:**
- Captures at 5 FPS (low CPU usage)
- Logs frame metadata to show FPS timing
- Efficient for monitoring scenarios

**FPS Guidelines:**
- **5 FPS**: Good for monitoring, very low CPU
- **15 FPS**: Balanced performance
- **30 FPS**: Smooth capture, higher CPU usage

**Configuration:**
```python
sources='screen://0!maxfps=5'
```

**Use cases:**
- Long-running monitoring
- Remote desktop streaming
- Resource-constrained systems

## Source URI Format

The ScreenIn filter uses the `screen://` URI scheme:

### Basic Format
```
screen://[monitor]?[params]!<options>
```

### Examples

**Monitor Selection:**
```python
'screen://0'              # Primary monitor
'screen://1'              # Secondary monitor
'screen://-1'             # All monitors (backend specific)
```

**Region Capture:**
```python
'screen://0?x=100&y=100&w=800&h=600'     # Using query params
'screen://0!x=100!y=100!width=800!height=600'  # Using options
```

**With Options:**
```python
'screen://0!maxfps=10'                    # 10 FPS
'screen://0!maxfps=15!backend=mss'        # 15 FPS with mss backend
'screen://0!resize=1280x720'              # Resize to 720p
```

**Multiple Sources:**
```python
'screen://0;main, screen://1;secondary'   # Two monitors with topics
```

## Configuration Options

### Monitor Selection
- `monitor=0`: Primary monitor (default)
- `monitor=1`: Secondary monitor
- `monitor=-1`: All monitors (backend specific)

### Region Parameters
- `x`: X coordinate of top-left corner
- `y`: Y coordinate of top-left corner
- `width` or `w`: Region width in pixels
- `height` or `h`: Region height in pixels

### Performance Options
- `maxfps`: Maximum frames per second (e.g., 5, 10, 15, 30)
- `resize`: Always resize to dimensions (e.g., '1280x720')
- `maxsize`: Maximum size limit (e.g., '1920x1080')
- `backend`: ScreenGear backend ('mss', 'dxcam', 'pil')

### Format Options
- `bgr`: Color format (true for BGR, false for RGB)

## Backend Selection

### Available Backends

#### `mss` (Default)
- **Cross-platform**: Works on Windows, macOS, Linux
- **Performance**: Good
- **Compatibility**: Best
- **Recommendation**: Default choice for all platforms

#### `dxcam` (Windows Only)
- **Platform**: Windows only
- **Performance**: Excellent (hardware accelerated)
- **Compatibility**: Requires DirectX
- **Recommendation**: Best for Windows

#### `pil` (Pillow)
- **Cross-platform**: Works everywhere
- **Performance**: Slower than mss
- **Compatibility**: Good
- **Recommendation**: Fallback option

### Backend Configuration

**Environment variable:**
```bash
export SCREEN_IN_BACKEND=mss
```

**Per-source:**
```python
sources='screen://0!backend=dxcam'
```

**Global default:**
```python
(ScreenIn, dict(
    sources='screen://0, screen://1',
    backend='mss',  # Applies to all sources
))
```

## Performance Optimization

### Reduce CPU Usage
1. **Lower FPS**: Use 5-10 FPS instead of 30
2. **Resize**: Capture at lower resolution
3. **Region capture**: Capture only needed area
4. **Backend**: Use dxcam on Windows for hardware acceleration

### Example: Optimized Configuration
```python
(ScreenIn, dict(
    sources='screen://0!maxfps=5!resize=1280x720',
    outputs='tcp://*:5550',
))
```

This captures at 5 FPS and resizes to 720p, significantly reducing CPU usage.

## Common Pipelines

### Screen Recording Pipeline
```python
Filter.run_multi([
    (ScreenIn, dict(
        sources='screen://0!maxfps=30',
        outputs='tcp://*:5550',
    )),
    (VideoOut, dict(
        sources='tcp://127.0.0.1:5550',
        outputs='file:///recordings/screen_{timestamp}.mp4',
    )),
])
```

### Screen Monitoring with Processing
```python
Filter.run_multi([
    (ScreenIn, dict(
        sources='screen://0!maxfps=10',
        outputs='tcp://*:5550',
    )),
    (Util, dict(
        sources='tcp://127.0.0.1:5550',
        outputs='tcp://*:5552',
        xforms='resize 800x600, box 0.1+0.1x0.3x0.05#ff0000',
    )),
    (Webvis, dict(
        sources='tcp://127.0.0.1:5552',
        port=8000,
    )),
])
```

### Multi-Monitor Recording
```python
Filter.run_multi([
    (ScreenIn, dict(
        sources='screen://0;mon0!maxfps=15, screen://1;mon1!maxfps=15',
        outputs='tcp://*:5550',
    )),
    (Webvis, dict(
        sources='tcp://127.0.0.1:5550',
        port=8000,
    )),
])
# Access: http://localhost:8000/mon0 and /mon1
```

## Troubleshooting

### Permission Denied (macOS)
**Problem:** Screen capture fails with permission error

**Solution:**
1. Open System Preferences → Security & Privacy → Privacy → Screen Recording
2. Add Python or your terminal to allowed apps
3. Restart terminal/IDE

### No Module Named 'mss'
**Problem:** `ModuleNotFoundError: No module named 'mss'`

**Solution:**
```bash
pip install mss
```

### Poor Performance
**Problem:** High CPU usage or low frame rate

**Solutions:**
1. Lower FPS: `maxfps=5` instead of `maxfps=30`
2. Resize capture: `resize=1280x720`
3. Use region capture: `screen://0?x=0&y=0&w=800&h=600`
4. Windows: Install dxcam for hardware acceleration

### ScreenGear Error
**Problem:** `ScreenGear initialization failed`

**Solutions:**
1. Check monitor index (use 0 for primary)
2. Verify backend is installed (`mss` is usually safest)
3. Try different backend: `backend=pil`

### Invalid Monitor Index
**Problem:** `Invalid monitor index` error

**Solution:**
- Use `monitor=0` for primary monitor
- Use `monitor=1` only if second monitor exists
- Check available monitors with `mss.mss().monitors`

## Advanced Usage

### Custom Processing Pipeline
```python
from openfilter.filter_runtime.filter import Filter
from openfilter.filter_runtime.filters.screen_in import ScreenIn
from openfilter.filter_runtime.filters.util import Util
from openfilter.filter_runtime.filters.webvis import Webvis

Filter.run_multi([
    (ScreenIn, dict(
        sources='screen://0?x=100&y=100&w=1024&h=768!maxfps=15',
        outputs='tcp://*:5550',
    )),
    (Util, dict(
        sources='tcp://127.0.0.1:5550',
        outputs='tcp://*:5552',
        xforms='resize 800x600, flipx',
    )),
    (Webvis, dict(
        sources='tcp://127.0.0.1:5552',
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

# Run example
python main.py
```

## Resources

- [ScreenIn Filter Documentation](../../docs/screen-in-filter.md)
- [VidGear ScreenGear Documentation](https://abhitronix.github.io/vidgear/latest/gears/screengear/)
- [OpenFilter Documentation](https://docs.openfilter.io/)

## Support

For issues or questions:
1. Check the [main documentation](../../docs/screen-in-filter.md)
2. Review [troubleshooting section](#troubleshooting)
3. Open an issue on the OpenFilter GitHub repository
